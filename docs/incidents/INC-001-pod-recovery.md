# INC-001 — Recuperação automática de pod Kubernetes

## Ambiente
- Projeto: CloudOps Reliability Lab
- Aplicação: Corporate Transactions API
- Plataforma: Kubernetes local com k3d
- Namespace: cloudops
- Deployment: transactions-api
- Réplicas desejadas: 2

## Cenário
Exclusão manual e controlada de um pod para simular a perda
de uma instância da aplicação.

## Ação executada
kubectl delete pod transactions-api-5b85cf5d44-gh9lw -n cloudops

## Evidências
- Pod original excluído com sucesso.
- ReplicaSet criou automaticamente um novo pod.
- Novo pod: transactions-api-5b85cf5d44-sms45.
- Novo pod agendado no nó agent-0.
- Deployment retornou ao estado de 2 réplicas disponíveis.
- Ambos os pods terminaram com status Running e Ready 1/1.

## Resultado
Recuperação automática da quantidade desejada de réplicas
sem intervenção manual para recriar o pod.

## Limitações
- O tempo exato de recuperação não foi medido.
- A disponibilidade contínua da API não foi medida.
- O teste não representa falha completa de um nó.

## Próximos passos
- Implementar Prometheus e Grafana.
- Medir latência, erros e disponibilidade.
- Executar testes com geração contínua de tráfego.
- Definir SLIs, SLOs e alertas.
