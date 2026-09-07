{{- define "graph-app.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "graph-app.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "graph-app.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "graph-app.labels" -}}
app.kubernetes.io/name: {{ include "graph-app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end }}

{{- define "graph-app.selectorLabels" -}}
app.kubernetes.io/name: {{ include "graph-app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "graph-app.databaseHost" -}}
{{- if .Values.postgresql.enabled -}}
{{ include "graph-app.fullname" . }}-postgresql
{{- else -}}
{{- .Values.postgresql.externalHost | default "postgres" -}}
{{- end -}}
{{- end }}

{{- define "graph-app.databaseUrl" -}}
{{- if .Values.postgresql.enabled -}}
postgresql://{{ .Values.postgresql.auth.username }}:{{ .Values.postgresql.auth.password }}@{{ include "graph-app.databaseHost" . }}:5432/{{ .Values.postgresql.auth.database }}
{{- else -}}
{{- .Values.secrets.databaseUrl -}}
{{- end -}}
{{- end }}

{{- define "graph-app.redisHost" -}}
{{- if .Values.redis.enabled -}}
{{ include "graph-app.fullname" . }}-redis
{{- else -}}
{{- .Values.redis.externalHost | default "redis" -}}
{{- end -}}
{{- end }}

{{- define "graph-app.redisUrl" -}}
{{- if .Values.redis.enabled -}}
redis://:{{ .Values.redis.auth.password }}@{{ include "graph-app.redisHost" . }}:6379
{{- else -}}
{{- .Values.secrets.redisUrl -}}
{{- end -}}
{{- end }}

{{- define "graph-app.rabbitmqHost" -}}
{{- if .Values.rabbitmq.enabled -}}
{{ include "graph-app.fullname" . }}-rabbitmq
{{- else -}}
{{- .Values.rabbitmq.externalHost | default "rabbitmq" -}}
{{- end -}}
{{- end }}

{{- define "graph-app.rabbitmqUrl" -}}
{{- if .Values.rabbitmq.enabled -}}
amqp://{{ .Values.rabbitmq.auth.username }}:{{ .Values.rabbitmq.auth.password }}@{{ include "graph-app.rabbitmqHost" . }}:5672
{{- else -}}
{{- .Values.secrets.rabbitMqUrl -}}
{{- end -}}
{{- end }}

{{- define "graph-app.weaviateHttpUrl" -}}
{{- if .Values.weaviate.enabled -}}
http://{{ include "graph-app.fullname" . }}-weaviate:8080
{{- else -}}
{{- .Values.weaviate.externalHttpUrl | default "http://weaviate:8080" -}}
{{- end -}}
{{- end }}

{{- define "graph-app.weaviateGrpcHost" -}}
{{- if .Values.weaviate.enabled -}}
{{ include "graph-app.fullname" . }}-weaviate
{{- else -}}
{{- .Values.weaviate.externalGrpcHost | default "weaviate" -}}
{{- end -}}
{{- end }}