{{/*
Common labels for ll-infra resources. Usage:
  labels:
    {{- include "ll-infra.labels" . | nindent 4 }}
*/}}
{{- define "ll-infra.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: layernetes
{{- end }}

{{/*
In-cluster URL of the bundled Gitea HTTP service (gitea subchart fullname
is "<release>-gitea" and its HTTP service is "<fullname>-http").
*/}}
{{- define "ll-infra.giteaInternalURL" -}}
http://{{ .Release.Name }}-gitea-http.{{ .Release.Namespace }}.svc.cluster.local:3000
{{- end }}

{{/*
Externally reachable Gitea base URL (scheme + host + optional port suffix).
*/}}
{{- define "ll-infra.giteaExternalURL" -}}
{{ .Values.global.urlScheme }}://{{ .Values.global.hosts.gitea }}{{ .Values.global.urlPortSuffix }}
{{- end }}
