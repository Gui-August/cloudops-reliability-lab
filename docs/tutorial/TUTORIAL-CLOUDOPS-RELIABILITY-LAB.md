# CloudOps Reliability Lab

**Relato técnico e tutorial de reprodução — versão 1.0**  
**Período documentado:** 2 a 5 de novembro de 2026 (alguns logs UTC já mostram 6 de novembro).  
**Repositório:** https://github.com/Gui-August/cloudops-reliability-lab  
**Ambiente:** Windows, PowerShell, Docker Desktop/WSL2 e Kubernetes local (k3d).

> **Nota de rastreabilidade:** este documento combina (a) comandos e resultados confirmados nos registros da execução e (b) comandos de reprodução compatíveis com o ambiente. Os itens de reprodução estão identificados como tal. Não afirmo ter executado comandos para os quais não há registro. O arquivo não inclui tokens, senhas, kubeconfigs ou dados secretos.

## 1. Objetivo

Criei o CloudOps Reliability Lab para estudar práticas de SRE, operações em Kubernetes e observabilidade, inicialmente com ferramentas locais e gratuitas. A aplicação simula operações corporativas, permitindo praticar monitoramento, tracing distribuído, recuperação de pods e, posteriormente, SLI/SLO e alertas.

Minha estratégia foi começar localmente, consolidar os fundamentos e só depois considerar Azure. O nome público do projeto é genérico, sem associação com empresas que inspiraram o estudo.

## 2. Ambiente e ferramentas

No computador Windows, utilizei PowerShell, Docker Desktop com WSL2, Git, Python, k3d e kubectl. Os registros do ambiente apontaram Docker Desktop 29.3.1, Docker Compose v5.1.0, Git 2.53.0.windows.3 e Python 3.14.6. O computador tinha aproximadamente 16 GB de RAM; o Docker Desktop disponibilizava cerca de 7,7 GiB à VM.

Pasta de trabalho:

```powershell
cd D:\Projeto\cloudops-reliability-lab
```

Comandos úteis para conferir ferramentas (procedimento de reprodução):

```powershell
docker version
docker compose version
git --version
python --version
kubectl version --client
k3d version
```

**Problema encontrado:** inicialmente, o Docker daemon não estava ativo. Iniciei o Docker Desktop, aguardei a inicialização do backend WSL2 e validei a conexão. Não foi necessário publicar serviços na nuvem.

## 3. Cluster Kubernetes com k3d

Antes de criar o cluster atual, encontrei contextos antigos de MicroK8s e k3d apontando para APIs inacessíveis. Para não confundir os ambientes, passei a especificar explicitamente o contexto nos comandos.

Comando de criação **confirmado no histórico**:

```powershell
k3d cluster create xp-sre-lab --servers 1 --agents 1 --api-port "127.0.0.1:6550" --wait --timeout 180s
```

O nome interno do cluster permaneceu `xp-sre-lab`, embora a identidade pública do projeto seja `cloudops-reliability-lab`. O contexto Kubernetes utilizado é `k3d-xp-sre-lab`.

Verificações usadas ao longo do laboratório:

```powershell
kubectl --context k3d-xp-sre-lab get nodes -o wide
kubectl --context k3d-xp-sre-lab get pods -A
kubectl --context k3d-xp-sre-lab top nodes
kubectl --context k3d-xp-sre-lab top pods -A
```

**Resultado observado:** dois nós Ready (`k3d-xp-sre-lab-server-0` e `k3d-xp-sre-lab-agent-0`), com K3s v1.31.5+k3s1. O metrics-server permitiu consultar consumo de CPU e memória.

## 4. Aplicação de transações em FastAPI

Implementei uma API de simulação de transações, com endpoints para saúde, readiness, criação de transações, simulação de erro, simulação de latência e métricas Prometheus.

| Endpoint | Função |
|---|---|
| `GET /` | Informações da aplicação |
| `GET /health` | Liveness |
| `GET /ready` | Readiness |
| `POST /transactions` | Simulação de transações |
| `GET /simulate/error` | Resposta HTTP 500 controlada |
| `GET /simulate/latency` | Atraso artificial de aproximadamente 3 segundos |
| `GET /metrics` | Métricas no formato Prometheus |

Arquivos centrais do repositório: `app/main.py`, `requirements.txt` e `Dockerfile`. A versão implantada e validada até o encerramento desta etapa é **1.1.0**. A versão 1.2.0, com métricas HTTP adicionais, foi preparada como proposta, mas **ainda não há confirmação de build ou implantação**.

A aplicação roda em um Deployment `transactions-api`, namespace `cloudops`, com **duas réplicas**, probes `/health` e `/ready`, requests de 50m CPU/64Mi e limites de 500m CPU/256Mi.

Comandos de inspeção e validação (procedimento de reprodução):

```powershell
kubectl --context k3d-xp-sre-lab get deployment transactions-api -n cloudops
kubectl --context k3d-xp-sre-lab get pods -n cloudops
kubectl --context k3d-xp-sre-lab describe deployment transactions-api -n cloudops
```

O fluxo de build e importação de imagens locais para k3d utiliza, como **referência de reprodução** (verificar o Dockerfile e o manifesto antes de executar):

```powershell
docker build -t cloudops-transactions-api:1.1.0 .
k3d image import cloudops-transactions-api:1.1.0 -c xp-sre-lab
kubectl --context k3d-xp-sre-lab rollout status deployment/transactions-api -n cloudops --timeout=180s
```

> O histórico confirma o build, a importação e o rollout bem-sucedidos da imagem 1.1.0, mas não preserva aqui a transcrição literal completa desses comandos. O bloco acima é um procedimento de reprodução, não uma transcrição.

## 5. Acesso local com port-forward

Usei `kubectl port-forward` para acessar serviços do cluster a partir do Windows. A janela do PowerShell deve permanecer aberta enquanto a conexão estiver em uso.

Comando utilizado para a API:

```powershell
kubectl --context k3d-xp-sre-lab port-forward -n cloudops svc/transactions-api 18000:80
```

**Incidente de operação:** ao tentar abrir outra sessão nas portas 18000 e 18001, recebi o erro de `bind` porque as duas já estavam ocupadas. Identifiquei os processos:

```powershell
Get-NetTCPConnection -LocalPort 18000,18001 -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, State, OwningProcess

Get-Process -Id 3852,15320 |
    Select-Object Id, ProcessName, Path
```

Os dois PIDs correspondiam ao `kubectl`. Confirmei que ambos os encaminhamentos respondiam à API:

```powershell
foreach ($porta in 18000,18001) {
    try {
        $resposta = Invoke-RestMethod -Uri "http://127.0.0.1:$porta/health" -TimeoutSec 3
        Write-Host "Porta $porta - API funcionando"
        $resposta
    }
    catch {
        Write-Host "Porta $porta - API não respondeu"
    }
}
```

**Resultado:** as portas 18000 e 18001 retornaram `healthy`. Reutilizei a conexão existente sem encerrar processos.

## 6. Observabilidade com Prometheus e Grafana

Configurei o namespace `observability` e implantei Prometheus **3.5.0** e Grafana **11.6.1**. O dashboard da aplicação foi provisionado por ConfigMap, e a configuração do Grafana passou a incluir fontes de dados de Prometheus e Jaeger.

Comandos de inspeção:

```powershell
kubectl --context k3d-xp-sre-lab get pods -n observability
kubectl --context k3d-xp-sre-lab get svc -n observability
kubectl --context k3d-xp-sre-lab get configmaps -n observability
```

Acesso local ao Grafana:

```powershell
kubectl --context k3d-xp-sre-lab port-forward -n observability svc/grafana 3000:3000
```

**Problemas enfrentados e resolvidos:** credencial administrativa do Grafana precisou ser redefinida; um dashboard JSON apresentou erro de leitura associado a caracteres de codificação/BOM; e ajustes no Deployment foram necessários para manter persistência e configuração de datasources. As senhas e arquivos de backup não foram incluídos no Git.

## 7. Persistência dos dados com PVC

No início, componentes de observabilidade utilizavam armazenamento efêmero. Migrei Grafana e Prometheus para PersistentVolumeClaims provisionados pela StorageClass `local-path`.

| PVC | Capacidade | Estado observado |
|---|---:|---|
| `grafana-storage` | 2 GiB | Bound |
| `prometheus-storage` | 5 GiB | Bound |

Verificações:

```powershell
kubectl --context k3d-xp-sre-lab get pvc -n observability
kubectl --context k3d-xp-sre-lab get storageclass
kubectl --context k3d-xp-sre-lab describe pvc grafana-storage -n observability
kubectl --context k3d-xp-sre-lab describe pvc prometheus-storage -n observability
```

Os Deployments foram ajustados para usar os PVCs. Foi necessário considerar o vínculo do volume ao nó local e usar estratégia `Recreate` quando apropriado. Fiz verificações de integridade e restauração do banco SQLite do Grafana, mantendo backups fora do controle de versão.

**Limitação:** PVC `local-path` em cluster local não equivale a armazenamento altamente disponível em produção; a retenção depende do ciclo de vida do cluster, dos nós e dos volumes.

## 8. Tracing com OpenTelemetry e Jaeger

Instrumentei a FastAPI com OpenTelemetry e configurei um Collector no namespace `observability`. A API exporta spans via OTLP/HTTP para:

```text
http://otel-collector.observability.svc.cluster.local:4318/v1/traces
```

O Collector recebe OTLP gRPC na porta 4317 e OTLP HTTP na 4318. Inicialmente encaminhava traces apenas ao Jaeger 2.11.0.

Arquivos principais: `observability/otel/otel-collector.yaml` e demais manifestos sob `observability/otel/`.

Comandos usados na validação:

```powershell
kubectl --context k3d-xp-sre-lab get pods -n observability
kubectl --context k3d-xp-sre-lab logs deployment/otel-collector -n observability --tail=50
kubectl --context k3d-xp-sre-lab port-forward -n observability svc/jaeger 16686:16686
```

Na aplicação, criei spans personalizados como `process_transaction`, `simulate_transaction_error` e `simulate_high_latency`. Também mantive métricas de negócio com Prometheus.

## 9. Incidente controlado INC-001 — Recuperação de pod

Realizei um exercício de recuperação de pod: excluí uma réplica da aplicação e observei o ReplicaSet criar outra para restaurar o estado desejado de duas réplicas. O relato está em `docs/incidents/INC-001-pod-recovery.md` no projeto.

Comandos equivalentes para reproduzir o exercício **somente em laboratório**:

```powershell
kubectl --context k3d-xp-sre-lab get pods -n cloudops
# Escolher conscientemente um pod da aplicação; não copiar um nome de outro ambiente.
kubectl --context k3d-xp-sre-lab delete pod <NOME_DO_POD> -n cloudops
kubectl --context k3d-xp-sre-lab get pods -n cloudops -w
```

**Resultado:** o Deployment voltou a 2/2 Ready. **Limitação:** isso testa substituição de pod, não falha de nó; não medi tempo de recuperação nem disponibilidade ponta a ponta. Não apresentar o experimento como teste completo de alta disponibilidade.

## 10. Dynatrace: segundo destino de traces

Criei um ambiente Dynatrace Public Trial e um token de API com permissão de ingestão de traces OpenTelemetry (`openTelemetryTrace.ingest`). O token **não foi colocado no YAML nem enviado ao GitHub**.

Configurei um Secret Kubernetes chamado `dynatrace-otel`, namespace `observability`, chave `api-token`. O Collector recebe o valor pela variável de ambiente `DT_API_TOKEN`:

```yaml
env:
  - name: DT_API_TOKEN
    valueFrom:
      secretKeyRef:
        name: dynatrace-otel
        key: api-token
```

Adicionei ao `observability/otel/otel-collector.yaml` o exporter:

```yaml
exporters:
  otlphttp/jaeger:
    endpoint: http://jaeger.observability.svc.cluster.local:4318
    tls:
      insecure: true
  otlphttp/dynatrace:
    endpoint: https://rew07917.live.dynatrace.com/api/v2/otlp
    headers:
      Authorization: "Api-Token ${env:DT_API_TOKEN}"
    timeout: 30s
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 120s
```

A pipeline `traces` foi configurada para exportar tanto ao Jaeger quanto ao Dynatrace. O exporter OTLP/HTTP acrescenta `/v1/traces` ao endpoint base.

**Comandos de validação e implantação confirmados:**

```powershell
cd D:\Projeto\cloudops-reliability-lab
Copy-Item '.\observability\otel\otel-collector.yaml' '.\observability\otel\otel-collector.yaml.bak' -Force
code '.\observability\otel\otel-collector.yaml'

kubectl --context k3d-xp-sre-lab apply --dry-run=server -f '.\observability\otel\otel-collector.yaml'
git diff --check
git status --short

kubectl --context k3d-xp-sre-lab apply -f '.\observability\otel\otel-collector.yaml'
kubectl --context k3d-xp-sre-lab rollout status deployment/otel-collector -n observability --timeout=180s
kubectl --context k3d-xp-sre-lab get pods -n observability
kubectl --context k3d-xp-sre-lab logs deployment/otel-collector -n observability --tail=50
```

**Falha encontrada:** o Collector inicialmente registrou `Configuration references empty environment variable` para `DT_API_TOKEN`. Investiguei:

```powershell
kubectl --context k3d-xp-sre-lab get deployment otel-collector -n observability -o jsonpath='{.spec.template.spec.containers[0].env}'
kubectl --context k3d-xp-sre-lab describe secret dynatrace-otel -n observability
```

O `describe secret` revelou `api-token: 0 bytes`. Recriei/corrigi o Secret com o token válido, sem publicar o valor. Depois reiniciei o Collector:

```powershell
kubectl --context k3d-xp-sre-lab rollout restart deployment/otel-collector -n observability
kubectl --context k3d-xp-sre-lab rollout status deployment/otel-collector -n observability --timeout=180s
kubectl --context k3d-xp-sre-lab logs deployment/otel-collector -n observability --tail=30
```

O Collector iniciou sem o aviso de variável vazia. Não documentei o valor do token nem um comando com token literal para evitar exposição.

## 11. Teste funcional e validação dos traces

Com o port-forward já ativo na porta 18000, gerei dez transações:

```powershell
1..10 | ForEach-Object {
    Invoke-RestMethod `
        -Uri 'http://127.0.0.1:18000/transactions' `
        -Method POST `
        -ContentType 'application/json' `
        -Body '{"amount":150.00,"currency":"BRL"}'
    Start-Sleep -Milliseconds 500
}
```

**Resultado observado:** as dez requisições retornaram transações com `status: approved`, moeda BRL e valor 150. O Collector não exibiu erros no período consultado:

```powershell
kubectl --context k3d-xp-sre-lab logs deployment/otel-collector -n observability --since=3m
```

No Dynatrace, confirmei visualmente traces de `POST /transactions`, com HTTP 200 e status Success. O print mostrava 20 requisições no conjunto exibido e durações individuais na faixa aproximada de 64–261 ms nas linhas visíveis. **Isso valida a ingestão de traces no Dynatrace**, não uma garantia de entrega de todos os spans em qualquer condição.

## 12. Métricas atuais e início do trabalho com SLI/SLO

Consultei `/metrics`:

```powershell
$metrics = (Invoke-WebRequest -Uri 'http://127.0.0.1:18000/metrics' -UseBasicParsing).Content
$metrics -split "`n" | Where-Object { $_ -match '^# (HELP|TYPE) ' }
$metrics -split "`n" | Where-Object { $_ -match 'error|request|http|transaction' -and $_ -notmatch '^#' } | Select-Object -First 35
```

As métricas disponíveis na versão 1.1.0 incluem:

- `corporate_transactions_total{status="approved"}`;
- `corporate_transaction_duration_seconds_bucket`;
- `corporate_transaction_duration_seconds_count`;
- `corporate_transaction_duration_seconds_sum`;
- métricas de processo Python e coleta de lixo.

Uma consulta local mostrou 20 transações aprovadas e 21 observações no histograma de duração. Esses contadores não precisam ser iguais, porque o histograma também é utilizado pela simulação de latência. **Não é possível calcular a disponibilidade HTTP completa apenas com essas métricas.**

Planejei a versão **1.2.0** com middleware para `http_requests_total`, `http_request_duration_seconds` e `http_requests_in_progress`, excluindo `/health`, `/ready` e `/metrics` dos SLIs de experiência. A proposta de código foi elaborada, mas **não há registro de que a versão 1.2.0 tenha sido salva, compilada, construída ou implantada**.

Metas **propostas, não aferidas**: disponibilidade de 99,9%, p95 de latência HTTP até 500 ms e taxa de 5xx até 0,1%. Ainda é necessário definir janela, população de requisições e tratamento de períodos sem tráfego.

## 13. Git e cuidados com informações sensíveis

Mantive o repositório público com arquivos de código e manifestos, excluindo credenciais, kubeconfigs e backups. O backup `otel-collector.yaml.bak` já estava ignorado pelo Git.

Verificações executadas antes de publicar a integração Dynatrace:

```powershell
git status --short
git check-ignore observability/otel/otel-collector.yaml.bak
Select-String -Path '.\observability\otel\otel-collector.yaml' -Pattern 'Authorization|DT_API_TOKEN|secretKeyRef|api-token'
git add observability/otel/otel-collector.yaml
git diff --cached --check
git diff --cached --stat
```

Commit e push **confirmados**:

```powershell
git commit -m 'feat: integrate Dynatrace OTLP tracing with OpenTelemetry'
git push origin main
git status
git log -1 --oneline
```

Resultado: commit `9373bbd`, branch `main`, sincronizada com `origin/main`, working tree clean. O repositório público está em https://github.com/Gui-August/cloudops-reliability-lab.

## 14. O que aprendi

1. A importância de identificar o contexto Kubernetes correto antes de investigar falhas de conectividade.
2. A diferença entre pod Running, Deployment Ready e entrega efetiva de telemetria.
3. Como PVCs ajudam a preservar dados, mas não substituem alta disponibilidade real.
4. Como depurar conflitos de porta sem encerrar processos arbitrariamente.
5. Como distribuir traces para Jaeger e Dynatrace a partir de um Collector OTLP.
6. Como diagnosticar Secret vazio com `kubectl describe secret` sem revelar credenciais.
7. Por que um teste de substituição de pod não prova recuperação de nó nem mede um SLO.
8. Por que métricas de negócio não bastam para medir disponibilidade HTTP.

## 15. Limitações e próximos passos

- Finalizar a instrumentação HTTP 1.2.0 e validar métricas agregadas das duas réplicas.
- Criar consultas PromQL, SLIs, SLOs, error budget e alertas.
- Documentar topologia de rede e fluxo de dados com diagrama próprio.
- Produzir README de navegação e guia de reprodução revisado a partir dos manifestos reais.
- Revisar todos os arquivos para evitar publicação de segredos ou dados sensíveis.
- Preparar publicação no LinkedIn com resultados comprovados, dificuldades e aprendizados.
- Avaliar uma futura evolução para Azure, com limites gratuitos e controle de custos.

---

**Reprodutibilidade:** nomes de imagens, arquivos e versões devem ser conferidos no repositório antes de executar procedimentos de reprodução. As configurações atuais dos manifestos versionados são a referência definitiva para o estado implantado. Este documento não substitui testes de segurança, disponibilidade ou carga de produção.
