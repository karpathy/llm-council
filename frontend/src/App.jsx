import { useState, useEffect, useRef } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import ModelSettings from './components/ModelSettings';
import { api } from './api';
import { FALLBACK_DEFAULTS, validSelection } from './modelSettings';
import './App.css';

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState('');
  const [models, setModels] = useState([]);
  const [defaults, setDefaults] = useState(FALLBACK_DEFAULTS);
  const [selection, setSelection] = useState(FALLBACK_DEFAULTS);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelNotice, setModelNotice] = useState('');
  const sending = useRef(false);
  const creating = useRef(false);

  useEffect(() => {
    let active = true;
    api.listConversations().then((items) => { if (active) setConversations(items); })
      .catch((failure) => { if (active) setError(failure.message); });
    api.listModels().then((catalog) => {
      if (!active) return;
      setModels(catalog.models);
      setDefaults(catalog.defaults);
      setSelection(catalog.defaults);
      if (!catalog.catalog_available) setModelNotice('OpenRouter’s catalog is unavailable. Enter a model ID manually or use the configured defaults. Availability will be checked when you send.');
    }).catch((failure) => {
      if (active) setModelNotice(`Could not load models: ${failure.message} Using fallback defaults; you can enter model IDs manually.`);
    }).finally(() => { if (active) setModelsLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!currentConversationId) return;
    let active = true;
    api.getConversation(currentConversationId).then((conversation) => {
      if (active) setCurrentConversation(conversation);
    }).catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [currentConversationId]);

  const refreshConversations = async () => {
    try { setConversations(await api.listConversations()); }
    catch (failure) { setError(failure.message); }
  };

  const handleNewConversation = async () => {
    if (sending.current || creating.current) return;
    creating.current = true;
    setIsCreating(true);
    setError('');
    try {
      const conversation = await api.createConversation();
      setConversations((items) => [{ id: conversation.id, created_at: conversation.created_at, message_count: 0 }, ...items]);
      setCurrentConversation(null);
      setCurrentConversationId(conversation.id);
    } catch (failure) { setError(failure.message); }
    finally { creating.current = false; setIsCreating(false); }
  };

  const handleSelectConversation = (id) => {
    if (sending.current || creating.current || id === currentConversationId) return;
    setError('');
    setCurrentConversation(null);
    setCurrentConversationId(id);
  };

  const handleSendMessage = async (content) => {
    if (!currentConversation || sending.current || modelsLoading) return;
    if (!validSelection(selection)) {
      setError('Choose 1–26 unique council models and a different model as chairman before sending.');
      return;
    }
    sending.current = true;
    setIsLoading(true);
    setError('');
    const id = currentConversationId;
    const updateAssistant = (updates) => setCurrentConversation((previous) => {
      if (previous?.id !== id) return previous;
      const messages = [...previous.messages];
      const last = messages[messages.length - 1];
      messages[messages.length - 1] = { ...last, ...updates, loading: { ...last.loading, ...updates.loading } };
      return { ...previous, messages };
    });
    setCurrentConversation((previous) => ({
      ...previous,
      messages: [...previous.messages, { role: 'user', content }, {
        role: 'assistant', stage1: null, stage2: null, stage3: null,
        metadata: null, loading: { stage1: false, stage2: false, stage3: false },
      }],
    }));
    try {
      await api.sendMessageStream(id, content, (type, event) => {
        switch (type) {
          case 'stage1_start': updateAssistant({ loading: { stage1: true } }); break;
          case 'stage1_complete': updateAssistant({ stage1: event.data, loading: { stage1: false } }); break;
          case 'stage2_start': updateAssistant({ loading: { stage2: true } }); break;
          case 'stage2_complete': updateAssistant({ stage2: event.data, metadata: event.metadata, loading: { stage2: false } }); break;
          case 'stage3_start': updateAssistant({ loading: { stage3: true } }); break;
          case 'stage3_complete': updateAssistant({ stage3: event.data, loading: { stage3: false } }); break;
          default: break;
        }
      }, selection);
    } catch (failure) {
      setError(`${failure.message} Your question is shown below. Check the conversation before starting a new attempt.`);
      updateAssistant({ error: failure.message });
    } finally {
      updateAssistant({ loading: { stage1: false, stage2: false, stage3: false } });
      sending.current = false;
      setIsLoading(false);
      refreshConversations();
    }
  };

  return (
    <div className="app">
      <Sidebar conversations={conversations} currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation} onNewConversation={handleNewConversation}
        disabled={isLoading || isCreating} />
      <main className="council-main">
        <ModelSettings models={models} selection={selection} defaults={defaults} onChange={setSelection}
          disabled={isLoading || modelsLoading} notice={modelsLoading ? 'Loading available models…' : modelNotice} />
        {error && <div className="app-error" role="alert">{error}<button type="button" onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
        <ChatInterface conversation={currentConversation} onSendMessage={handleSendMessage}
          isLoading={isLoading} sendDisabled={modelsLoading || !validSelection(selection)} />
      </main>
    </div>
  );
}

export default App;
