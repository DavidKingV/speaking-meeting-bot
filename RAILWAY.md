# Desplegar el bot de Teams en Railway (solo OpenAI)

Este fork usa **OpenAI Realtime** (speech-to-speech) en lugar de Deepgram + Cartesia.
El bot completo (oído + cerebro + voz) corre con **una sola key: `OPENAI_API_KEY`**.
MeetingBaaS es quien mete el bot a la reunión de Teams/Meet/Zoom.

## Qué se cambió respecto al repo original

- `scripts/meetingbaas.py`: el pipeline ahora usa `OpenAIRealtimeLLMService`
  (STT + LLM + TTS + turn detection en un WebSocket). Se quitaron `DeepgramSTTService`,
  `CartesiaTTSService`, `OpenAILLMService` y el VAD local (Silero) — Realtime hace VAD server-side.
- `.env.example`: Deepgram/Cartesia comentados; añadidos `OPENAI_REALTIME_MODEL` y `OPENAI_REALTIME_VOICE`.
- `railway.json`: fuerza build por Dockerfile (evita que Railway elija Nixpacks y falle con las deps de audio).
- El extra `openai` de `pipecat-ai` ya incluye el servicio Realtime → `pyproject.toml` no se tocó.

## Prerrequisitos

1. **Cuenta MeetingBaaS** (https://meetingbaas.com) → API key.
2. **Key de OpenAI** con acceso al modelo `gpt-realtime` y saldo (Realtime cobra audio in/out por minuto — es el costo dominante).
3. **Fork de este repo** en tu GitHub (Railway despliega desde ahí).

## Pasos en Railway

1. New Project → **Deploy from GitHub repo** → elige tu fork.
2. Railway detecta `railway.json` y construye con el **Dockerfile**.
3. En **Variables**, define:

   | Variable | Valor |
   |---|---|
   | `MEETING_BAAS_API_KEY` | tu key de MeetingBaaS |
   | `OPENAI_API_KEY` | tu key de OpenAI |
   | `OPENAI_REALTIME_MODEL` | `gpt-realtime` (opcional) |
   | `OPENAI_REALTIME_VOICE` | `marin` (o alloy, cedar, echo…) |
   | `BASE_URL` | la URL pública de Railway, con `https://` (ver paso 4) |

   > **NO** definas `DEEPGRAM_API_KEY` ni `CARTESIA_API_KEY` — ya no se usan.
   > `PORT` lo inyecta Railway automáticamente; el Dockerfile ya lo respeta.

4. **BASE_URL**: en Settings → Networking, genera un dominio público
   (p.ej. `https://tu-app.up.railway.app`). Cópialo tal cual en `BASE_URL` y
   **redeploy**. MeetingBaaS necesita esa URL para abrir el WebSocket de audio hacia tu bot.

5. Verifica que arrancó: abre `https://tu-app.up.railway.app/health` → debe responder
   `{"status":"ok", ...}` y `/docs` debe mostrar el Swagger.

## Lanzar el bot en una reunión de Teams

1. Crea una reunión de Teams y copia el link de invitación.
2. Lanza el bot con la persona **`voxcare_coach`** (ya incluida, ver abajo):

   ```bash
   curl -X POST https://tu-app.up.railway.app/bots \
     -H "Content-Type: application/json" \
     -H "x-meeting-baas-api-key: TU_MEETINGBAAS_KEY" \
     -d '{
       "meeting_url": "https://teams.microsoft.com/l/meetup-join/...",
       "personas": ["voxcare_coach"]
     }'
   ```

   > El header y el body los define `app/routes.py` (auth por `x-meeting-baas-api-key`,
   > body con `meeting_url` + `personas`). Revisa `/docs` para el esquema exacto.

3. Admite el bot desde el lobby de Teams. **Éxito =** aparece como participante, te
   escucha y responde por voz con la personalidad de la persona.

4. Para sacarlo: `DELETE /bots/{bot_id}` con el mismo header.

## Personas

Cada persona vive en `config/personas/<nombre>/` con `README.md` (prompt/personalidad),
y opcionalmente `Content.md` (conocimiento) y `Rules.md`. El `prompt` del README se
convierte en las `instructions` del modelo Realtime. El campo `cartesia_voice_id` de los
README ya no aplica; la voz se elige con el campo `openai_voice:` en el bloque Metadata
del README (o, como fallback, `OPENAI_REALTIME_VOICE`).

### Prompt guardado en OpenAI (opcional, en vez del README)

Si ya tienes un **Prompt** creado en platform.openai.com/prompts (con su `pmpt_...` ID),
puedes usarlo en lugar del texto del README:

- **Global** (todas las personas): variables de entorno `OPENAI_PROMPT_ID` /
  `OPENAI_PROMPT_VERSION` en Railway.
- **Por persona**: campos `openai_prompt_id:` / `openai_prompt_version:` en el bloque
  `Metadata` del `README.md` de esa persona (tienen prioridad sobre las variables globales).

Cuando hay un `prompt_id` activo, el bot manda `session.prompt = {id, version}` a Realtime
y **no** envía el texto del README como `instructions` (para no competir con el prompt
guardado). **Si no configuras ningún `prompt_id`**, todo sigue funcionando como hoy: el
texto del README es la fuente de las instrucciones. Es decir, el README actúa como
fallback automático — no hace falta borrarlo ni tocarlo si decides usar un prompt guardado.

### Persona VoxCare (incluida)

`config/personas/voxcare_coach/README.md` reproduce el agente **VoxCare English Coach
(Andrea)** de tu dashboard de OpenAI: el prompt completo va en el cuerpo del README y
`openai_voice: sage` en Metadata. Los demás parámetros de tu sesión del dashboard
(`server_vad` con threshold 0.5 / padding 300ms / silence 500ms, `noise_reduction:
far_field`, transcripción `gpt-realtime-whisper`, `max_output_tokens: 2016`,
`output_modalities: ["audio"]`, y `reasoning.effort: low` solo si usas `gpt-realtime-2`)
están aplicados en `scripts/meetingbaas.py` y ajustables por variables de entorno
(`OPENAI_REALTIME_*`).

> **Nota sobre el flujo:** el endpoint `POST /v1/realtime/client_secrets` de tu dashboard
> es para el flujo WebRTC del navegador (tokens efímeros). Este bot se conecta
> **server-to-server por WebSocket** usando tu `OPENAI_API_KEY` directamente, así que no
> se "importa" el agente por su ID: se **replica su configuración** (prompt + parámetros),
> que es exactamente lo que ya está hecho aquí.

## Diagnóstico rápido

- **Bot entra pero no habla ni oye**: casi siempre es el modelo `gpt-realtime` no habilitado
  en tu cuenta OpenAI, o `OPENAI_API_KEY` sin saldo. Revisa logs de Railway: busca
  `[LLM] OpenAI Realtime initialized` y errores de conexión WS a `api.openai.com`.
- **Bot nunca se une**: `MEETING_BAAS_API_KEY` inválida o `BASE_URL` mal puesta (sin https
  o con dominio viejo). MeetingBaaS no puede abrir el WebSocket de vuelta.
- **Costo alto**: es esperado con Realtime. Para bajarlo, revierte `scripts/meetingbaas.py`
  al pipeline de 3 servicios (Deepgram + Cartesia) — está en el historial de git.
