
import { useState, useEffect, useRef } from "react";
import {
  Send,
  Plus,
  Bot,
  User,
  Trash2,
  Menu,
  Sparkles,
  Loader2
} from "lucide-react";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

import "highlight.js/styles/github-dark.css";
import "./App.css";

const API_URL = "http://localhost:8000";

function App() {

  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const bottomRef = useRef(null);
  const textareaRef = useRef(null);
  const abortRef = useRef(null);

  // =====================================
  // LOAD SAVED CHATS
  // =====================================

  const loadHistory = async () => {

    try {

      const response = await fetch(`${API_URL}/chats`);

      if (!response.ok) {
        throw new Error("Unable to load chat history");
      }

      const data = await response.json();

      setHistory(data.chats || []);

    } catch (error) {

      console.error("History error:", error);

    }
  };

  useEffect(() => {

    loadHistory();

    return () => {
      abortRef.current?.abort();
    };

  }, []);

  // =====================================
  // AUTO SCROLL
  // =====================================

  useEffect(() => {

    bottomRef.current?.scrollIntoView({
      behavior: "smooth"
    });

  }, [messages, loading]);

  // =====================================
  // NEW CHAT
  // =====================================

  const newChat = () => {

    abortRef.current?.abort();

    setMessages([]);
    setQuestion("");
    setActiveChat(null);
    setLoading(false);

  };

  // =====================================
  // OPEN SAVED CHAT
  // =====================================

  const openChat = async (chat) => {

    if (loading) return;

    try {

      const response = await fetch(
        `${API_URL}/chats/${chat.id}`
      );

      if (!response.ok) {
        throw new Error("Unable to open conversation");
      }

      const data = await response.json();

      setActiveChat(chat.id);
      setMessages(data.messages || []);

    } catch (error) {

      console.error(error);
      alert(error.message);

    }
  };

  // =====================================
  // DELETE CHAT
  // =====================================

  const deleteChat = async (id) => {

    if (!window.confirm("Delete this conversation?")) {
      return;
    }

    try {

      const response = await fetch(
        `${API_URL}/chats/${id}`,
        { method: "DELETE" }
      );

      if (!response.ok) {
        throw new Error("Unable to delete conversation");
      }

      if (activeChat === id) {
        newChat();
      }

      await loadHistory();

    } catch (error) {

      alert(error.message);

    }
  };

  // =====================================
  // SEND MESSAGE WITH STREAMING
  // =====================================

  const sendMessage = async () => {

    const text = question.trim();

    if (!text || loading) return;

    const userMessage = {
      role: "user",
      content: text
    };

    setMessages(previous => [
      ...previous,
      userMessage,
      {
        role: "assistant",
        content: ""
      }
    ]);

    setQuestion("");
    setLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {

      const response = await fetch(
        `${API_URL}/ask`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "text/event-stream"
          },
          body: JSON.stringify({
            question: text,
            chat_id: activeChat
          }),
          signal: controller.signal
        }
      );

      if (!response.ok) {

        const errorData = await response.json();

        throw new Error(
          errorData.detail || `HTTP ${response.status}`
        );
      }

      if (!response.body) {
        throw new Error("Streaming is not supported by this response");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = "";
      let streamCompleted = false;

      const updateAssistant = (token) => {

        setMessages(previous => {

          const updated = [...previous];
          const lastIndex = updated.length - 1;

          if (
            lastIndex >= 0 &&
            updated[lastIndex].role === "assistant"
          ) {

            updated[lastIndex] = {
              ...updated[lastIndex],
              content: updated[lastIndex].content + token
            };

          }

          return updated;

        });

      };

      const processEvent = (event) => {

        const dataLine = event
          .split("\n")
          .find(line => line.startsWith("data:"));

        if (!dataLine) return;

        const payload = JSON.parse(
          dataLine.slice(5).trim()
        );

        if (payload.token) {
          updateAssistant(payload.token);
        }

        if (payload.chat_id) {
          setActiveChat(payload.chat_id);
        }

        if (payload.error) {
          throw new Error(payload.error);
        }

        if (payload.done) {
          streamCompleted = true;
        }

      };

      while (true) {

        const { value, done } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, {
          stream: true
        });

        const events = buffer.split("\n\n");

        buffer = events.pop() || "";

        for (const event of events) {
          processEvent(event);
        }

      }

      buffer += decoder.decode();

      if (buffer.trim()) {
        processEvent(buffer);
      }

      if (!streamCompleted) {
        throw new Error("AI response stream ended unexpectedly");
      }

      await loadHistory();

    } catch (error) {

      if (error.name === "AbortError") {
        return;
      }

      console.error("Chat error:", error);

      setMessages(previous => {

        const updated = [...previous];
        const lastIndex = updated.length - 1;

        if (
          lastIndex >= 0 &&
          updated[lastIndex].role === "assistant"
        ) {

          updated[lastIndex] = {
            ...updated[lastIndex],
            content: `Error: ${error.message}`
          };

        }

        return updated;

      });

    } finally {

      setLoading(false);
      abortRef.current = null;

      textareaRef.current?.focus();

    }
  };

  // =====================================
  // RENDER UI
  // =====================================

  return (

    <div className="app">

      {/* SIDEBAR */}

      <aside className={`sidebar ${sidebarOpen ? "" : "closed"}`}>

        <div className="sidebar-header">

          <h2>
            <Sparkles size={20} />
            My AI
          </h2>

          <button onClick={() => setSidebarOpen(false)}>
            <Menu size={20} />
          </button>

        </div>

        <button className="new-chat" onClick={newChat}>
          <Plus size={18} />
          New Chat
        </button>

        <p className="history-label">CHAT HISTORY</p>

        <div className="history-list">

          {history.map(chat => (

            <div
              className={`history-item ${
                activeChat === chat.id ? "active" : ""
              }`}
              key={chat.id}
            >

              <button onClick={() => openChat(chat)}>
                {chat.title}
              </button>

              <button
                className="delete-btn"
                onClick={() => deleteChat(chat.id)}
                title="Delete conversation"
              >
                <Trash2 size={15} />
              </button>

            </div>

          ))}

        </div>

        <div className="sidebar-footer">

          <Bot size={18} />

          <span>Qwen 2.5 · 3B</span>

          <span className="online-dot"></span>

        </div>

      </aside>

      {/* MAIN */}

      <main className="main">

        <header className="topbar">

          {!sidebarOpen && (

            <button onClick={() => setSidebarOpen(true)}>
              <Menu size={20} />
            </button>

          )}

          <span>My AI Assistant</span>

          <span className="model-tag">
            Qwen 2.5 3B
          </span>

        </header>

        {/* CHAT AREA */}

        <section className="chat-area">

          {messages.length === 0 ? (

            <div className="welcome">

              <div className="welcome-icon">
                <Sparkles size={30} />
              </div>

              <h1>What can I help you with?</h1>

              <p>
                Your own AI assistant powered by Qwen 2.5.
              </p>

              <div className="suggestions">

                {[
                  "Explain Docker architecture",
                  "Write a Python script",
                  "Explain Jenkins CI/CD",
                  "How does Kubernetes work?"
                ].map(item => (

                  <button
                    key={item}
                    onClick={() => setQuestion(item)}
                  >
                    {item}
                  </button>

                ))}

              </div>

            </div>

          ) : (

            <div className="messages">

              {messages.map((message, index) => (

                <div
                  className={`message ${message.role}`}
                  key={index}
                >

                  <div className="avatar">

                    {message.role === "user"
                      ? <User size={19} />
                      : <Bot size={19} />
                    }

                  </div>

                  <div className="message-content">

                    <strong>
                      {message.role === "user"
                        ? "You"
                        : "My AI"
                      }
                    </strong>

                    {message.content ? (

                      <div className="markdown-content">

                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          rehypePlugins={[rehypeHighlight]}
                        >
                          {message.content}
                        </ReactMarkdown>

                      </div>

                    ) : loading && message.role === "assistant" ? (

                      <p className="typing">
                        <Loader2 size={16} className="spin" />
                        Thinking...
                      </p>

                    ) : null}

                  </div>

                </div>

              ))}

              <div ref={bottomRef} />

            </div>

          )}

        </section>

        {/* INPUT */}

        <div className="input-wrapper">

          <div className="input-box">

            <textarea
              ref={textareaRef}
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={e => {

                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {

                  e.preventDefault();
                  sendMessage();

                }

              }}
              placeholder="Ask anything..."
              rows={1}
              disabled={loading}
            />

            <button
              className="send-btn"
              onClick={sendMessage}
              disabled={!question.trim() || loading}
              title="Send message"
            >

              {loading
                ? <Loader2 size={19} className="spin" />
                : <Send size={19} />
              }

            </button>

          </div>

          <p className="disclaimer">
            My AI can make mistakes. Verify important information.
          </p>

        </div>

      </main>

    </div>

  );

}

export default App;

