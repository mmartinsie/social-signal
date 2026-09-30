{{/* Labels shared by every object of the chart. */}}
{{- define "socialsignal-db.labels" -}}
app.kubernetes.io/part-of: socialsignal
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/*
Selector labels. The component label is what the NetworkPolicies match;
the instance label keeps the Services from ever selecting the
verify-boundary test pods, which only carry the component label (D12).
*/}}
{{- define "socialsignal-db.selectorLabels" -}}
app.kubernetes.io/component: postgres
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
