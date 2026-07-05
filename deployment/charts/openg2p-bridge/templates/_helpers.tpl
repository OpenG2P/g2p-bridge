{{/*
Env for the pm-register Job: Partner Manager URLs, the admin token creds (a Keycloak
client holding the partner_manager role), the Bridge's OWN signing .p12 (→ registers
PARTNER_G2P_BRIDGE, production too) and — only when signature validation is on — the
committed test cert + test-partner ids. Reads global only.
*/}}
{{- define "openg2p-bridge.pmSeedEnv" -}}
{{- $g := .Values.global -}}
{{- $sk := $g.g2pBridgeSigningKey -}}
{{- $testIds := list -}}
{{- if and $g.testPartnerEnabled $g.g2pBridgeSignatureValidationEnabled -}}
{{- range $g.testPartnerMnemonics -}}
{{- $testIds = append $testIds (printf "PARTNER_%s" .) -}}
{{- end -}}
{{- end -}}
- name: SANITY_VERIFY_TLS
  value: {{ $g.g2pBridgeVerifyTls | default false | quote }}
- name: SANITY_PM_PARTNER_API_URL
  value: {{ tpl $g.partnerManagementApiUrl $ | quote }}
- name: SANITY_PM_ADMIN_URL
  value: {{ tpl $g.partnerManagementAdminApiUrl $ | quote }}
- name: SANITY_PM_TOKEN_URL
  value: "{{ tpl $g.keycloakIssuerUrl $ }}/protocol/openid-connect/token"
- name: SANITY_PM_CLIENT_ID
  value: {{ $g.pmSeedClientId | default "commons-services-staff-portal" | quote }}
- name: SANITY_PM_CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ $g.pmSeedClientId | default "commons-services-staff-portal" | quote }}
      key: client_secret
      optional: true
- name: SANITY_PM_ALGORITHM
  value: {{ $g.g2pBridgeSigningAlgorithm | default "RS256" | quote }}
# Self: the Bridge's own key, derived from the signing .p12 (mounted by the Job).
- name: SANITY_PM_SELF_PARTNER_IDS
  value: {{ ternary "PARTNER_G2P_BRIDGE" "" $g.g2pBridgeSparSignRequestsEnabled | quote }}
- name: SANITY_PM_SIGNING_KEY_PATH
  value: "{{ $sk.mountPath }}/{{ $sk.secretKey }}"
- name: SANITY_PM_SIGNING_KEY_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ tpl $sk.secretName $ | quote }}
      key: {{ $sk.passwordSecretKey | quote }}
      optional: true
- name: SANITY_PM_SELF_KID
  value: {{ $g.g2pBridgeSigningKeyKid | default "" | quote }}
# Test partners (only when signature validation is enabled) from the committed cert.
- name: SANITY_PM_TEST_PARTNER_IDS
  value: {{ join "," $testIds | quote }}
- name: SANITY_PM_TEST_CERT_PEM
  value: {{ $g.testPartnerCertPem | default "" | quote }}
- name: SANITY_PM_TEST_KID
  value: {{ $g.testPartnerKid | default "" | quote }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "g2pBridgeApi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "g2pBridgeApi.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{/*
Render Env values section
*/}}
{{- define "g2pBridgeApi.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "g2pBridgeApi.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "g2pBridgeApi.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "benePortalApi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "benePortalApi.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{/*
Render Env values section
*/}}
{{- define "benePortalApi.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "benePortalApi.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "benePortalApi.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "g2pBridgeProducer.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "g2pBridgeProducer.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{/*
Render Env values section
*/}}
{{- define "g2pBridgeProducer.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "g2pBridgeProducer.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "g2pBridgeProducer.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "g2pBridgeWorker.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "g2pBridgeWorker.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{/*
Render Env values section
*/}}
{{- define "g2pBridgeWorker.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "g2pBridgeWorker.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "g2pBridgeWorker.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{/* ===================== Example Bank (bundled) ===================== */}}

{{- define "exampleBankApi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{- define "exampleBankApi.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{- define "exampleBankApi.baseEnvVars" -}}
{{- $context := .context -}}
{{- range $k, $v := .envVars }}
- name: {{ $k }}
{{- if or (kindIs "int64" $v) (kindIs "float64" $v) (kindIs "bool" $v) }}
  value: {{ $v | quote }}
{{- else if kindIs "string" $v }}
  value: {{ include "common.tplvalues.render" ( dict "value" $v "context" $context ) | squote }}
{{- else }}
  valueFrom: {{- include "common.tplvalues.render" ( dict "value" $v "context" $context ) | nindent 4}}
{{- end }}
{{- end }}
{{- end -}}

{{- define "exampleBankApi.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "exampleBankApi.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{- define "exampleBankBeat.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{- define "exampleBankBeat.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{- define "exampleBankBeat.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "exampleBankApi.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}

{{- define "exampleBankWorker.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "common.names.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{- define "exampleBankWorker.imagePullSecrets" -}}
{{- include "common.images.pullSecrets" (dict "images" (list .Values.image .Values.postgresCheckerInit.image) "global" .Values.global) -}}
{{- end -}}

{{- define "exampleBankWorker.envVars" -}}
{{- $envVars := merge (deepCopy .Values.envVars) (deepCopy .Values.envVarsFrom) -}}
{{- include "exampleBankApi.baseEnvVars" (dict "envVars" $envVars "context" $) }}
{{- end -}}
