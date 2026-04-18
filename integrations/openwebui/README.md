# Open WebUI Integrations for OpenRAG

## Feedback Forwarder

A pipeline function for Open WebUI that forwards user feedback (thumbs up/down) to OpenRAG's feedback management system.

### Installation

1. In Open WebUI, go to **Admin Panel** > **Functions**
2. Click **Create Function**
3. Paste the contents of `feedback_forwarder.py`
4. Configure the Valves:
   - `openrag_url`: Your OpenRAG API URL (e.g., `http://openrag:8000`)
   - `service_key`: The value of `FEEDBACK_SERVICE_KEY` from your OpenRAG `.env`
   - `enabled`: Toggle on/off

### How it works

The function acts as an **outlet** — it intercepts every model response and checks for feedback annotations. When a user clicks thumbs up/down on a response, Open WebUI adds an `annotation` field to the message. The function:

1. Detects messages with annotations containing a `rating`
2. Extracts the question (previous user message) and response
3. Sends the feedback to OpenRAG's `/admin/feedback/ingest` endpoint
4. All sending happens in a background thread to avoid blocking the response

### OpenRAG Configuration

Set the `FEEDBACK_SERVICE_KEY` environment variable in your OpenRAG deployment:

```env
FEEDBACK_SERVICE_KEY=your-secret-key-here
```
