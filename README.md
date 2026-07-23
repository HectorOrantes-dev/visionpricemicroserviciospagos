# VisionPrice — Microservicio de Pasarela de Pagos

Microservicio de suscripciones/mensualidades para **Vision Price**, con dos pasarelas:
**Conekta** y **PayPal**. Hecho en **Python + FastAPI**, **PostgreSQL** y **Docker**,
siguiendo **arquitectura hexagonal**.

## Capacidades

- Activar mensualidad (suscripción) recurrente con Conekta (tarjeta) o PayPal.
- Checkout hospedado de Conekta (link de pago) con **tarjeta, OXXO (efectivo) o
  SPEI (transferencia)** en la misma pantalla — pago único que otorga vigencia
  de plan al confirmarse (ver [Flujo Conekta Checkout](#flujo-conekta-checkout-tarjeta-oxxo-spei)).
- Asociar / desasociar tarjeta (Conekta).
- Cancelar suscripción / pagos.
- Historial de suscripciones del usuario (cuántas ha tenido, estados).
- Webhooks de ambos proveedores para mantener el estado sincronizado.
- Autenticación por **JWT** emitido por VisionPrice (este servicio solo lo valida).

## Planes

| plan_key            | Nombre | Precio  | Conekta (env)          | PayPal (env)           |
|---------------------|--------|---------|------------------------|------------------------|
| `vision-price-pro`  | Pro    | 349 MXN | `CONEKTA_PLAN_PRO`     | `PAYPAL_PLAN_PRO`      |
| `vision-price-plan` | Plan   | 899 MXN | `CONEKTA_PLAN_EQUIPOS` | `PAYPAL_PLAN_EQUIPOS`  |

## Estructura (arquitectura hexagonal)

```
main.py                       App factory FastAPI
src/
  shared/        config, database, models, repos (puerto + SQL), plan_catalog, errors, schemas
  oauth/         verificación de JWT  -> get_current_user
  conekta/       domain (entities/puertos) · application (use cases) · infraestructure (adapters/routers/DI)
  paypal/        idem, con OAuth2 + verificación de webhook
scripts/         bootstrap_paypal.py · bootstrap_conekta.py
alembic/         migraciones (0001_initial = 3 tablas)
Dockerfile · docker-compose.yml
```

## Puesta en marcha (Docker)

1. Copia y completa el entorno:
   ```bash
   cp .env.example .env
   ```
   **Obligatorio:** define `JWT_SECRET` con el **mismo** secreto que usa VisionPrice
   para firmar sus tokens (HS256). Sin esto la autenticación rechaza todo.

2. Levanta todo (API + Postgres + migraciones):
   ```bash
   docker compose up --build
   ```
   - La API corre `alembic upgrade head` automáticamente al arrancar.
   - Docs interactivas: http://localhost:8000/docs
   - Healthcheck: http://localhost:8000/health

## Crear los planes de PayPal (una sola vez)

Los `PAYPAL_PLAN_*` vienen vacíos. Genera los planes (Pro 349 / Plan 899 MXN):

```bash
# con el contenedor arriba:
docker compose exec api python -m scripts.bootstrap_paypal
```

Copia las líneas `PAYPAL_PLAN_PRO=...` y `PAYPAL_PLAN_EQUIPOS=...` que imprime a tu
`.env` y reinicia: `docker compose up -d`.

(Opcional) Verifica/crea los planes de Conekta:
```bash
docker compose exec api python -m scripts.bootstrap_conekta
```

## Endpoints

Todos requieren `Authorization: Bearer <jwt>` salvo `/health` y los `/webhook`.

| Método | Ruta                                      | Descripción                              |
|--------|-------------------------------------------|------------------------------------------|
| GET    | `/health`                                 | Liveness                                 |
| POST   | `/conekta/subscriptions`                  | `{plan_key, card_token}` → activa (recurrente, solo tarjeta) |
| POST   | `/conekta/subscriptions/cancel`           | Cancela la activa del usuario            |
| POST   | `/conekta/checkout`                       | `{plan_key, allowed_payment_methods?}` → `{checkout_url,...}` (tarjeta/OXXO/SPEI, pago único) |
| GET    | `/conekta/checkout/{id}`                  | Estado de un checkout del usuario        |
| DELETE | `/conekta/payment-method`                 | Desasocia la tarjeta                     |
| POST   | `/conekta/webhook`                        | Eventos de Conekta                       |
| POST   | `/paypal/subscriptions`                   | `{plan_key}` → devuelve `approval_url`   |
| POST   | `/paypal/subscriptions/{id}/cancel`       | Cancela una suscripción de PayPal        |
| POST   | `/paypal/webhook`                         | Eventos de PayPal (firma verificada)     |
| GET    | `/subscriptions`                          | Historial del usuario                    |
| GET    | `/subscriptions/active`                   | Suscripciones activas/pendientes         |

### Flujo PayPal (resumen)
1. `POST /paypal/subscriptions` → guarda la suscripción `pending` y devuelve `approval_url`.
2. Rediriges al usuario a `approval_url`; aprueba en PayPal.
3. PayPal envía `BILLING.SUBSCRIPTION.ACTIVATED` a `/paypal/webhook` → pasa a `active`.

### Flujo Conekta (resumen) — tarjeta recurrente
1. El frontend tokeniza la tarjeta con **Conekta.js** y obtiene `card_token`.
2. `POST /conekta/subscriptions {plan_key, card_token}` → crea customer + suscripción `active`.
   Conekta vuelve a cobrar automáticamente cada mes (esto SÍ es recurrente).

### Flujo Conekta Checkout (tarjeta, OXXO, SPEI)

OXXO y SPEI **no son recurrentes** en Conekta (no hay forma de que Conekta le
vuelva a cobrar solo a una referencia de efectivo o una CLABE). Por eso este
flujo usa el **Checkout hospedado** de Conekta (el "link de pago" del
dashboard): una página de Conekta donde el usuario elige método, y un pago
único que otorga `plan.period_days` (30 días por default) de vigencia sobre
su suscripción — para renovar, genera un checkout nuevo.

1. `POST /conekta/checkout {plan_key, allowed_payment_methods?}` (JWT del
   usuario). `allowed_payment_methods` es opcional — subconjunto de
   `["card","cash","bank_transfer"]` (`cash`=OXXO, `bank_transfer`=SPEI); si
   se omite, usa `CONEKTA_CHECKOUT_PAYMENT_METHODS` del `.env` (los tres).
   Responde `{id, checkout_url, status: "pending", expires_at, ...}`.
2. Rediriges/abres `checkout_url` (página de Conekta) — ahí el usuario elige
   tarjeta, OXXO o SPEI y completa el pago (o, si eligió OXXO/SPEI, ve la
   referencia/barcode o CLABE para pagar después).
3. Cuando Conekta confirma el pago, manda `order.paid` a `/conekta/webhook`.
   El servicio identifica el checkout por `metadata.internal_ref` (se manda
   al crear el checkout, no depende de cómo Conekta anide el id internamente),
   marca el `checkout_order` como `paid` y otorga la vigencia (activa o
   extiende la suscripción del usuario). Idempotente: si el webhook llega
   duplicado, no se vuelve a otorgar vigencia.
4. `GET /conekta/checkout/{id}` deja consultar el estado (`pending` / `paid`
   / `expired` / `cancelled`) — útil para una pantalla de "esperando pago",
   pero la activación real ocurre por el webhook, no por este endpoint.

## Webhooks

Registra las URLs públicas en cada dashboard:
- Conekta → `https://TU_DOMINIO/conekta/webhook`
- PayPal  → `https://TU_DOMINIO/paypal/webhook` y copia el `Webhook ID` resultante a
  `PAYPAL_WEBHOOK_ID` (se usa para verificar la firma).

## Pasar Conekta a producción

1. Cambia `CONEKTA_PRIVATE_KEY` por la **`key_live_...`** de producción.
2. Asegura que los planes existen en producción con los montos correctos:
   `docker compose exec api python -m scripts.bootstrap_conekta`.
3. Reinicia. El código no cambia: el ambiente lo determina la API key.

## Desarrollo local (sin Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Postgres local y DATABASE_URL apuntando a él (asyncpg)
alembic upgrade head
uvicorn main:app --reload
```

## Seguridad

- `.env` está en `.gitignore`: nunca lo subas.
- **Rota** las credenciales de PayPal/Conekta si se compartieron fuera de un canal seguro.
