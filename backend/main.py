"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator
from typing import List, Dict, Any
import uuid
import json
import asyncio

from . import storage
from .config import OPENROUTER_API_KEY, COUNCIL_MODELS, CHAIRMAN_MODEL, validate_distinct_chairman
from .model_catalog import list_model_options
from .research import research_summary
from .council import run_full_council, generate_conversation_title, stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final, calculate_aggregate_rankings

app = FastAPI(title="LLM Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    council_models: List[str] | None = Field(default=None, min_length=1, max_length=26)
    chairman_model: str | None = None
    research: StrictBool = False

    @field_validator("council_models")
    @classmethod
    def validate_council_models(cls, value):
        if value is None:
            return value
        models = [cls.validate_model_id(model) for model in value]
        if len(models) != len(set(models)):
            raise ValueError("Council models must be unique.")
        return models

    @field_validator("chairman_model")
    @classmethod
    def validate_chairman_model(cls, value):
        return None if value is None else cls.validate_model_id(value)

    @model_validator(mode="after")
    def validate_distinct_roles(self):
        validate_distinct_chairman(
            COUNCIL_MODELS if self.council_models is None else self.council_models,
            CHAIRMAN_MODEL if self.chairman_model is None else self.chairman_model,
        )
        return self

    @staticmethod
    def validate_model_id(value):
        model = value.strip()
        if not model or len(model) > 200 or "/" not in model or any(char.isspace() for char in model):
            raise ValueError("Use a nonempty OpenRouter model ID such as provider/model.")
        return model


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/models")
async def get_models():
    """Public text-model choices and defaults; never return or send API keys."""
    return await list_model_options()


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Set OPENROUTER_API_KEY in the project .env file and restart the backend.",
        )

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Run the 3-stage council process
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content, request.council_models, request.chairman_model, request.research
    )

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result
    )

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Set OPENROUTER_API_KEY in the project .env file and restart the backend.",
        )

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        title_task = None
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # Start title generation in parallel (don't await yet)
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))

            # Stage 1: Collect responses
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results = await stage1_collect_responses(request.content, request.council_models, request.research)
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            if not stage1_results:
                message = "No council models responded. Check your OpenRouter key, credits, model IDs, and backend logs."
                if request.research:
                    message = "Research failed: no council member returned a usable answer. Check model tool support, your OpenRouter key, credits, and backend logs."
                    summary = research_summary(COUNCIL_MODELS if request.council_models is None else request.council_models, [])
                    failure = {"model": "error", "response": message, "research": summary, "citations": []}
                    storage.add_assistant_message(conversation_id, [], [], failure)
                    yield f"data: {json.dumps({'type': 'stage3_complete', 'data': failure})}\n\n"
                yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"
                return

            # Stage 2: Collect rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(request.content, stage1_results, request.council_models, request.research)
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            metadata = {"label_to_model": label_to_model, "aggregate_rankings": aggregate_rankings}
            if request.research:
                metadata["research"] = research_summary(COUNCIL_MODELS if request.council_models is None else request.council_models, stage1_results, stage2_results)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': metadata})}\n\n"

            # Stage 3: Synthesize final answer
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(request.content, stage1_results, stage2_results, request.chairman_model, request.research, request.council_models)
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            if title_task and not title_task.done():
                title_task.cancel()
                await asyncio.gather(title_task, return_exceptions=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
