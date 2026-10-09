#!/usr/bin/env python3
"""
Via Carraria — KEDA Queue-Driven Scale-to-Zero Verification Script
Tests rapid scale-out upon queue message burst and verified scale-down to 0 replicas
upon queue drain and cooldown expiration.

Usage:
    python3 test_keda_scaling.py [--namespace NAMESPACE] [--messages NUM_MESSAGES] [--cooldown SECONDS]
"""

import argparse
import json
import subprocess
import sys
import time


def run_cmd(cmd: list[str]) -> str:
    """Executes a subprocess command and returns stdout."""
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed ({' '.join(cmd)}): {res.stderr.strip()}")
    return res.stdout.strip()


def get_replicas(namespace: str, deployment: str) -> int:
    """Queries Kubernetes for the current replica count of a deployment."""
    cmd = [
        "kubectl",
        "get",
        "deployment",
        deployment,
        "-n",
        namespace,
        "-o",
        "jsonpath={.status.replicas}",
    ]
    out = run_cmd(cmd)
    return int(out) if out else 0


def get_queue_depth(namespace: str, rabbitmq_pod: str, queue_name: str) -> int:
    """Queries RabbitMQ queue depth via rabbitmqctl inside the cluster."""
    cmd = [
        "kubectl",
        "exec",
        "-n",
        namespace,
        rabbitmq_pod,
        "--",
        "rabbitmqctl",
        "list_queues",
        "name",
        "messages",
        "--formatter",
        "json",
    ]
    try:
        out = run_cmd(cmd)
        data = json.loads(out)
        for q in data:
            if q.get("name") == queue_name:
                return int(q.get("messages", 0))
    except Exception:
        pass
    return 0


def publish_messages(namespace: str, rabbitmq_pod: str, queue_name: str, count: int):
    """Publishes synthetic document ingestion jobs to the target RabbitMQ queue."""
    print(f"==> Injecting {count} synthetic processing jobs into '{queue_name}'...")
    payload = json.dumps({"sourceId": "bench-src-001", "graphId": "graph-cs", "action": "parse"})
    for i in range(count):
        cmd = [
            "kubectl",
            "exec",
            "-n",
            namespace,
            rabbitmq_pod,
            "--",
            "rabbitmqadmin",
            "-u",
            "rabbitmq",
            "-p",
            "minikubepassword",
            "publish",
            "exchange=amq.default",
            f"routing_key={queue_name}",
            f"payload={payload}",
        ]
        run_cmd(cmd)
    print(f"==> {count} messages successfully published.")


def purge_queue(namespace: str, rabbitmq_pod: str, queue_name: str):
    """Purges the target queue to trigger KEDA scale-down cooldown."""
    print(f"==> Purging RabbitMQ queue '{queue_name}'...")
    cmd = [
        "kubectl",
        "exec",
        "-n",
        namespace,
        rabbitmq_pod,
        "--",
        "rabbitmqadmin",
        "-u",
        "rabbitmq",
        "-p",
        "minikubepassword",
        "purge",
        f"queue={queue_name}",
    ]
    run_cmd(cmd)
    print("==> Queue successfully purged.")


def test_keda_scaling(namespace: str, count: int, cooldown_sec: int):
    print("=" * 70)
    print("       VIA CARRARIA — KEDA SCALE-TO-ZERO EMPIRICAL VERIFICATION")
    print("=" * 70)
    print(f"Target Namespace:       {namespace}")
    print(f"Synthetic Job Count:    {count}")
    print(f"Configured Cooldown:    {cooldown_sec} seconds")
    print("=" * 70)

    # 1. Identify RabbitMQ Pod
    rabbitmq_pods = run_cmd([
        "kubectl",
        "get",
        "pods",
        "-n",
        namespace,
        "-l",
        "app.kubernetes.io/component=rabbitmq",
        "-o",
        "jsonpath={.items[0].metadata.name}",
    ])
    if not rabbitmq_pods:
        print("[ERROR] RabbitMQ pod not found in namespace", namespace)
        sys.exit(1)
    print(f"Found RabbitMQ Pod:     {rabbitmq_pods}")

    parsing_deploy = "viacarraria-graph-app-parsing-worker"
    embedding_deploy = "viacarraria-graph-app-embedding-engine"
    queue_name = "document_parsing_queue"

    # 2. Check Initial Replicas
    print("\n[Phase 1] Validating Initial Idle State (Expect: 0 replicas)...")
    p_reps = get_replicas(namespace, parsing_deploy)
    e_reps = get_replicas(namespace, embedding_deploy)
    print(f"  • {parsing_deploy}:   {p_reps} replicas")
    print(f"  • {embedding_deploy}: {e_reps} replicas")

    # 3. Publish Message Burst
    print("\n[Phase 2] Triggering Burst Scale-Up...")
    t0 = time.time()
    publish_messages(namespace, rabbitmq_pods, queue_name, count)

    print("==> Waiting for KEDA to detect queue depth and scale deployments...")
    scaled_up = False
    for step in range(30):
        time.sleep(2)
        p_reps = get_replicas(namespace, parsing_deploy)
        e_reps = get_replicas(namespace, embedding_deploy)
        elapsed = time.time() - t0
        sys.stdout.write(f"\r  [{elapsed:4.1f}s] parsing-worker: {p_reps} pods | embedding-engine: {e_reps} pods")
        sys.stdout.flush()
        if p_reps > 0 and e_reps > 0:
            scaled_up = True
            print(f"\n[SUCCESS] Both deployments successfully scaled out in {elapsed:.1f}s!")
            break

    if not scaled_up:
        print("\n[TIMEOUT] Scale-up did not trigger within 60s.")
        sys.exit(1)

    # 4. Drain Queue & Observe Cooldown
    print("\n[Phase 3] Draining Queue & Monitoring Cooldown Period...")
    purge_queue(namespace, rabbitmq_pods, queue_name)

    print(f"==> Observing KEDA cooldown ({cooldown_sec}s target)...")
    t_purge = time.time()
    scaled_to_zero = False

    while (time.time() - t_purge) < (cooldown_sec + 40):
        time.sleep(2)
        p_reps = get_replicas(namespace, parsing_deploy)
        e_reps = get_replicas(namespace, embedding_deploy)
        elapsed = time.time() - t_purge
        sys.stdout.write(f"\r  [{elapsed:4.1f}s cooldown] parsing-worker: {p_reps} pods | embedding-engine: {e_reps} pods")
        sys.stdout.flush()
        if p_reps == 0 and e_reps == 0:
            scaled_to_zero = True
            print(f"\n[SUCCESS] Scale-to-Zero confirmed! Both deployments returned to 0 replicas in {elapsed:.1f}s.")
            break

    if not scaled_to_zero:
        print("\n[WARNING] Deployments did not scale to 0 before observation window expired.")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("                    KEDA SCALE-TO-ZERO TEST PASSED")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Via Carraria KEDA Queue-Driven Scale-to-Zero Verification"
    )
    parser.add_argument(
        "-n",
        "--namespace",
        type=str,
        default="viacarraria",
        help="Kubernetes namespace (default: viacarraria)",
    )
    parser.add_argument(
        "-m",
        "--messages",
        type=int,
        default=5,
        help="Number of messages to inject into queue (default: 5)",
    )
    parser.add_argument(
        "-c",
        "--cooldown",
        type=int,
        default=20,
        help="Expected cooldown period in seconds (default: 20)",
    )
    args = parser.parse_args()

    test_keda_scaling(args.namespace, args.messages, args.cooldown)


if __name__ == "__main__":
    main()
