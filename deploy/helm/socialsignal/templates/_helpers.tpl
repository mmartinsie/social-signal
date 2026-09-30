{{/* Labels shared by every object of the chart. */}}
{{- define "socialsignal.labels" -}}
app.kubernetes.io/part-of: socialsignal
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/* Egress rule: DNS (53 UDP/TCP) towards the cluster DNS pods only. */}}
{{- define "socialsignal.egressDNS" -}}
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: {{ .Values.dns.namespace }}
      podSelector:
        matchLabels:
          {{- toYaml .Values.dns.podLabels | nindent 10 }}
  ports:
    - protocol: UDP
      port: 53
    - protocol: TCP
      port: 53
{{- end }}

{{/* Egress rule: PostgreSQL in the data zone. */}}
{{- define "socialsignal.egressPostgres" -}}
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: {{ .Values.namespaces.data }}
      podSelector:
        matchLabels:
          app.kubernetes.io/component: postgres
  ports:
    - protocol: TCP
      port: {{ .Values.ports.postgres }}
{{- end }}
