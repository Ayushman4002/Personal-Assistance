import { useState } from "react";
import {
  MessageSquare, Search, Mail, ArrowUp, PanelLeft, PanelLeftClose,
  RefreshCw, ChevronLeft, Send, X, Check, LoaderCircle, AlertCircle,
  ExternalLink, Copy, Inbox
} from "lucide-react";
import "./App.css";

const API = "http://127.0.0.1:8000";
const agents = [
  { id: "chat", label: "AI Chat", icon: MessageSquare },
  { id: "research", label: "Research Agent", icon: Search },
  { id: "email", label: "Email Agent", icon: Mail },
];

function textOf(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(textOf).join("\n");
  if (typeof value === "object") {
    if (value.content != null) return textOf(value.content);
    if (value.text != null) return textOf(value.text);
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function extractEmails(raw) {
  if (Array.isArray(raw)) return raw;
  if (raw && typeof raw === "object") {
    for (const key of ["emails", "messages", "data", "results"]) {
      if (Array.isArray(raw[key])) return raw[key];
    }
  }
  const value = textOf(raw);
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) return parsed;
    for (const key of ["emails", "messages", "data", "results"]) {
      if (Array.isArray(parsed?.[key])) return parsed[key];
    }
  } catch { /* Backend may return plain text. */ }
  return [];
}

function extractNews(raw) {
  if (Array.isArray(raw)) return raw;
  if (raw && typeof raw === "object") {
    for (const key of ["news", "articles", "results", "items"]) {
      if (Array.isArray(raw[key])) return raw[key];
    }
  }
  try {
    const parsed = JSON.parse(textOf(raw));
    if (Array.isArray(parsed)) return parsed;
    for (const key of ["news", "articles", "results", "items"]) {
      if (Array.isArray(parsed?.[key])) return parsed[key];
    }
  } catch { /* Show the raw response when it isn't structured JSON. */ }
  return [];
}

export default function App() {
  const [agent, setAgent] = useState("chat");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [emails, setEmails] = useState([]);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [emailContent, setEmailContent] = useState("");
  const [replyInstruction, setReplyInstruction] = useState("");
  const [draft, setDraft] = useState(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [news, setNews] = useState([]);
  const [researchText, setResearchText] = useState("");
  const [view, setView] = useState("home");

  async function apiPost(path, body) {
    const response = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
    return data;
  }

  function reportError(err) {
    setError(err?.message || "Something went wrong.");
  }

  function selectAgent(next) {
    setAgent(next);
    setView("home");
    setError("");
    setNotice("");
    setSelectedEmail(null);
    setEmailContent("");
    setDraft(null);
    setReplyInstruction("");
    if (next === "email") void loadEmails();
    if (next === "research") {
      setNews([]);
      setResearchText("");
    }
  }

  async function sendChat(message = input) {
    const prompt = message.trim();
    if (!prompt || loading) return;
    setMessages((old) => [...old, { role: "user", content: prompt }]);
    setInput("");
    setLoading(true);
    setError("");
    try {
      const data = await apiPost("/chat", { message: prompt, agent: "chat" });
      setMessages((old) => [...old, { role: "assistant", content: textOf(data.response ?? data) }]);
    } catch (err) {
      reportError(err);
    } finally {
      setLoading(false);
    }
  }

  async function loadEmails() {
    setLoading(true);
    setError("");
    try {
      const data = await apiPost("/chat", {
        message: "Show my latest five emails", agent: "email", action: "list_emails",
      });
      const raw = data.response ?? data;
      setEmails(extractEmails(raw));
      setResearchText(textOf(raw));
      setNotice("");
    } catch (err) {
      reportError(err);
    } finally {
      setLoading(false);
    }
  }

  async function openEmail(email) {
    const id = email.id ?? email.email_id ?? email.message_id;
    if (!id) return setError("This email has no detectable message ID in the backend response.");
    setSelectedEmail(email);
    setView("email-detail");
    setDraft(null);
    setLoading(true);
    setError("");
    try {
      const data = await apiPost("/chat", {
        message: "Read this email", agent: "email", action: "read_email", email_id: id,
      });
      setEmailContent(textOf(data.response ?? data));
    } catch (err) {
      reportError(err);
    } finally {
      setLoading(false);
    }
  }

  async function generateReply() {
    const id = selectedEmail?.id ?? selectedEmail?.email_id ?? selectedEmail?.message_id;
    if (!id || !replyInstruction.trim()) return;
    setDraftLoading(true);
    setError("");
    try {
      const data = await apiPost("/chat", {
        message: "Draft a professional reply based on my instructions.",
        agent: "email", action: "draft_reply", email_id: id,
        user_instruction: replyInstruction.trim(),
      });
      if (!data.draft_id || !data.draft) throw new Error("Backend did not return a draft ID and draft text.");
      setDraft(data);
      setNotice("Review the draft. Nothing has been sent.");
    } catch (err) {
      reportError(err);
    } finally {
      setDraftLoading(false);
    }
  }

  async function sendDraft() {
    if (!draft?.draft_id || !window.confirm(`Send this email to ${draft.to || "the recipient"}?`)) return;
    setDraftLoading(true);
    setError("");
    try {
      await apiPost("/email/send", { draft_id: draft.draft_id });
      setDraft(null);
      setReplyInstruction("");
      setNotice("Email sent successfully.");
      setView("home");
      await loadEmails();
    } catch (err) {
      reportError(err);
    } finally {
      setDraftLoading(false);
    }
  }

  async function cancelDraft() {
    if (!draft?.draft_id) return;
    setDraftLoading(true);
    try {
      await apiPost("/email/cancel", { draft_id: draft.draft_id });
      setDraft(null);
      setReplyInstruction("");
      setNotice("Draft cancelled. No email was sent.");
    } catch (err) {
      reportError(err);
    } finally {
      setDraftLoading(false);
    }
  }

  async function runResearch() {
    setLoading(true);
    setError("");
    setNews([]);
    setResearchText("");
    try {
      const data = await apiPost("/chat", {
        message: "Find the top 10 latest AI and technology news stories. Include title, source, URL, and a short summary for each.",
        agent: "research",
      });
      const raw = data.response ?? data;
      setNews(extractNews(raw));
      setResearchText(textOf(raw));
    } catch (err) {
      reportError(err);
    } finally {
      setLoading(false);
    }
  }

  async function openNews(item) {
    const title = item.title || item.headline || "this news story";
    const url = item.url || item.link || "";
    setMessages((old) => [...old, { role: "user", content: `More details about: ${title}${url ? ` (${url})` : ""}` }]);
    setAgent("research");
    setView("research-detail");
    setLoading(true);
    setError("");
    try {
      const data = await apiPost("/chat", {
        message: `Give me more details and a summary of this AI/technology news story: "${title}". Source URL: ${url}`,
        agent: "research",
      });
      setMessages((old) => [...old, { role: "assistant", content: textOf(data.response ?? data) }]);
    } catch (err) {
      reportError(err);
    } finally {
      setLoading(false);
    }
  }

  const activeAgent = agents.find((item) => item.id === agent);

  return (
    <div className="app-shell">
      {sidebarOpen && <aside className="sidebar">
        <div className="sidebar-top">
          <h2>Agents</h2>
          <button className="icon-button" title="Close sidebar" onClick={() => setSidebarOpen(false)}><PanelLeftClose size={18} /></button>
        </div>
        <nav className="agent-nav">
          {agents.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${agent === id ? "active" : ""}`} onClick={() => selectAgent(id)}>
            <Icon size={18} strokeWidth={1.8} /><span>{label}</span>
          </button>)}
        </nav>
      </aside>}

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            {!sidebarOpen && <button className="icon-button" title="Open sidebar" onClick={() => setSidebarOpen(true)}><PanelLeft size={19} /></button>}
            <span className="k3ai-title">K3AI</span>
          </div>
          <div className="topbar-right"><span className="agent-label">{activeAgent?.label}</span></div>
        </header>

        {error && <div className="error-banner"><AlertCircle size={17} /><span>{error}</span><button className="icon-button" onClick={() => setError("")}><X size={16} /></button></div>}
        {notice && <div className="notice-banner"><Check size={16} /><span>{notice}</span><button className="icon-button" onClick={() => setNotice("")}><X size={15} /></button></div>}

        <div className="content-scroll">
          {agent === "chat" && <section className={`chat-view ${messages.length ? "has-messages" : ""}`}>
            {messages.length > 0 && <div className="message-list">
              {messages.map((message, index) => <div className={`message-row ${message.role}`} key={`${index}-${message.role}`}>
                <div className={`message-avatar ${message.role}`}>{message.role === "assistant" ? "K" : "You"}</div>
                <div className="message-body"><div className="message-author">{message.role === "assistant" ? "K3AI" : "You"}</div><div className="message-content">{message.content}</div></div>
              </div>)}
              {loading && <div className="loading-line"><LoaderCircle size={17} className="spin" /> Thinking...</div>}
            </div>}
            <div className="composer-wrap">
              <form className="composer" onSubmit={(event) => { event.preventDefault(); void sendChat(); }}>
                <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="Message K3AI..." rows={1} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendChat(); } }} />
                <div className="composer-bottom"><span className="composer-hint">Enter to send · Shift + Enter for new line</span><button className="send-button" type="submit" disabled={!input.trim() || loading} aria-label="Send message">{loading ? <LoaderCircle size={17} className="spin" /> : <ArrowUp size={19} />}</button></div>
              </form>
              <div className="disclaimer">AI can make mistakes. Verify important information.</div>
            </div>
          </section>}

          {agent === "research" && <section className="agent-page">
            <div className="page-heading"><div><h1>Research Agent</h1><p>Latest AI and technology news.</p></div><button className="secondary-button" onClick={() => void runResearch()} disabled={loading}><RefreshCw size={16} /> {loading ? "Researching…" : "What's New?"}</button></div>
            {news.length > 0 ? <div className="news-list">{news.map((item, index) => <article className="news-card" key={item.url || item.link || index}>
              <div><h3>{item.title || item.headline || `News item ${index + 1}`}</h3><p>{item.summary || item.description || item.snippet || ""}</p><span className="muted-text">{item.source || item.publisher || ""}</span></div>
              <div className="news-actions"><button className="secondary-button" onClick={() => void openNews(item)}>More details</button>{(item.url || item.link) && <a href={item.url || item.link} target="_blank" rel="noreferrer" aria-label="Open source"><ExternalLink size={16} /></a>}</div>
            </article>)}</div> : researchText ? <pre className="raw-response">{researchText}</pre> : <div className="empty-panel"><Search size={25} /><p>Run a search to discover recent AI and technology news.</p><button className="secondary-button" onClick={() => void runResearch()} disabled={loading}>{loading ? "Researching…" : "What's New?"}</button></div>}
            {view === "research-detail" && <div className="message-list">{messages.filter((message) => message.role === "assistant").slice(-1).map((message, index) => <div className="message-content" key={index}>{message.content}</div>)}</div>}
          </section>}

          {agent === "email" && <section className="agent-page">
            {view === "email-detail" && selectedEmail ? <>
              <button className="back-button" onClick={() => { setView("home"); setDraft(null); }}><ChevronLeft size={17} /> Back to inbox</button>
              <div className="page-heading"><div><h1>{selectedEmail.subject || "Email details"}</h1><p>{selectedEmail.from || selectedEmail.sender || "Unknown sender"} · {selectedEmail.date || ""}</p></div></div>
              <div className="email-body">{loading ? "Loading email…" : emailContent}</div>
              <div className="reply-panel"><h3>Draft a reply</h3><textarea value={replyInstruction} onChange={(event) => setReplyInstruction(event.target.value)} placeholder="What should the reply say?" rows={3} /><button className="secondary-button" onClick={() => void generateReply()} disabled={draftLoading || !replyInstruction.trim()}>{draftLoading ? "Preparing…" : "Generate draft"}</button></div>
              {draft && <div className="draft-panel"><h3>Review draft</h3><p><strong>To:</strong> {draft.to || ""}</p><textarea value={draft.draft} readOnly rows={8} /><p className="muted-text">This preview is read-only. Review the saved draft before sending.</p><div className="button-row"><button className="secondary-button" onClick={() => void cancelDraft()} disabled={draftLoading}>Cancel draft</button><button className="primary-button" onClick={() => void sendDraft()} disabled={draftLoading}><Send size={15} /> Send email</button></div></div>}
            </> : <>
              <div className="page-heading"><div><h1>Email Agent</h1><p>Review your latest emails and draft replies.</p></div><button className="secondary-button" onClick={() => void loadEmails()} disabled={loading}><RefreshCw size={16} /> Refresh inbox</button></div>
              {emails.length > 0 ? <div className="email-list">{emails.map((email, index) => <button className="email-card" key={email.id || email.email_id || email.message_id || index} onClick={() => void openEmail(email)}>
                <span className="email-card-icon"><Mail size={17} /></span><span className="email-card-main"><strong>{email.subject || "No subject"}</strong><span>{email.from || email.sender || "Unknown sender"}</span><small>{email.snippet || email.body || email.text || "Open to read this email"}</small></span><span className="muted-text">{email.date || ""}</span>
              </button>)}</div> : <div className="empty-panel"><Inbox size={25} /><p>{loading ? "Loading inbox…" : "No emails to display yet."}</p>{researchText && !loading && <pre className="raw-response">{researchText}</pre>}<button className="secondary-button" onClick={() => void loadEmails()} disabled={loading}>Load inbox</button></div>}
            </>}
          </section>}
        </div>
      </main>
    </div>
  );
}
