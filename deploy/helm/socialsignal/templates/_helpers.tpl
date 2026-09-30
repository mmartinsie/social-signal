{{/* Labels shared by every object of the chart. */}}
{{- define "socialsignal.labels" -}}
app.kubernetes.io/part-of: socialsignal
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/* Pod security context shared by every workload: non-root, seccomp. */}}
{{- define "socialsignal.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
fsGroup: 10001
seccompProfile:
  type: RuntimeDefault
{{- end }}

{{/* Container security context shared by every workload. */}}
{{- define "socialsignal.containerSecurityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: [ALL]
{{- end }}

{{/*
Database connection of a component (D13): user and password come from its
zone's own Secret, the password as a mounted file so it is not in the
process environment. Call with (dict "root" $ "secret" <Secret name>); the
volume and its mount below go with it.
*/}}
{{- define "socialsignal.databaseEnv" -}}
- name: DB_HOST
  value: {{ .root.Values.database.host | quote }}
- name: DB_PORT
  value: {{ .root.Values.database.port | quote }}
- name: DB_NAME
  value: {{ .root.Values.database.name | quote }}
- name: DB_USER
  valueFrom:
    secretKeyRef:
      name: {{ .secret }}
      key: username
- name: DB_PASSWORD_FILE
  value: /run/secrets/db/password
{{- end }}

{{- define "socialsignal.databaseVolumeMount" -}}
- name: db-credentials
  mountPath: /run/secrets/db
  readOnly: true
{{- end }}

{{- define "socialsignal.databaseVolume" -}}
- name: db-credentials
  secret:
    secretName: {{ .secret }}
    items:
      - key: password
        path: password
    defaultMode: 0440
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
