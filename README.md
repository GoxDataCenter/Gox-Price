# GOX Pricing Platform

Sistema de precificação para linhas: Acronis, Fortinet FWaaS, Bare Metal e Colocation.

## Recursos

- Login com perfis (`admin`, `sales`)
- Página principal com cards das 4 linhas
- Catálogo dinâmico por linha via API
- Importação de price list `.xlsx` por fornecedor (admin)
- Configurações por linha (imposto, markup, custo hora)
- Motor de cálculo centralizado no backend
- Endpoint para integração IXC com preço final por quote

## Estrutura

- `backend/app/main.py`: API FastAPI + regras de cálculo + banco SQLite
- `frontend/src/App.jsx`: aplicação React
- `docker-compose.yml`: orquestra backend e frontend

## Subir com Docker Compose

```bash
cd pricing_system
docker compose up -d --build
```

Acesso:
- Frontend: `http://localhost:8088`
- API (via proxy): `http://localhost:8088/api/health`

Para derrubar:

```bash
docker compose down
```

Para derrubar removendo volume do banco:

```bash
docker compose down -v
```

## Usuários padrão

- `admin / admin123`
- `vendas / vendas123`

## Formato esperado da planilha

Colunas obrigatórias:
- `part` (SKU)
- `desc` (descrição)
- `price` (custo unitário)

Coluna opcional:
- `type` (ex: HW, SERV, STORAGE)

## Endpoints principais

- `POST /api/auth/login`
- `GET /api/catalog/{line}`
- `GET /api/admin/settings/{line}`
- `PUT /api/admin/settings/{line}`
- `POST /api/admin/import-price-list`
- `POST /api/pricing/calculate`
- `GET /api/integrations/ixc/quote/{quote_id}`
