"use client";

import { useRef, useState, type KeyboardEvent } from "react";

interface Props {
  onSend: (content: string) => void;
  onStop?: () => void;
  disabled?: boolean;
}

export default function MessageInput({ onSend, onStop, disabled = false }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function onInput() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  return (
    <div className="border-t border-border bg-surface px-4 py-4 shrink-0">
      <div className="mx-auto flex max-w-3xl items-end gap-3">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          onInput={onInput}
          placeholder={disabled ? "waiting…" : "message kairo… (enter to send, shift+enter for newline)"}
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none overflow-hidden rounded-xl border bg-surface-2
                     px-4 py-3 text-sm text-text placeholder:text-text-muted
                     disabled:opacity-40 transition-all duration-200"
          style={{
            fontFamily: "var(--font-noto), sans-serif",
            borderColor: "var(--color-border)",
            outline: "none",
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "var(--color-primary)";
            e.currentTarget.style.boxShadow =
              "0 0 0 3px rgba(139,92,246,0.2), 0 0 16px rgba(139,92,246,0.15)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "var(--color-border)";
            e.currentTarget.style.boxShadow = "none";
          }}
        />
        {disabled && onStop ? (
          <button
            onClick={onStop}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl
                       text-white transition-all duration-200"
            style={{
              background: "linear-gradient(135deg, #EC4899, #8B5CF6)",
            }}
            aria-label="stop"
            title="stop generating"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="currentColor"
              className="h-4 w-4"
            >
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        ) : (
        <button
          onClick={submit}
          disabled={disabled || !value.trim()}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl
                     text-white transition-all duration-200
                     disabled:opacity-30"
          style={{
            background: "linear-gradient(135deg, #EC4899, #8B5CF6)",
          }}
          onMouseEnter={(e) => {
            if (!(e.currentTarget as HTMLButtonElement).disabled) {
              (e.currentTarget as HTMLButtonElement).style.boxShadow =
                "0 0 16px rgba(139,92,246,0.5)";
            }
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.boxShadow = "none";
          }}
          aria-label="send"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="h-4 w-4"
          >
            <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
          </svg>
        </button>
        )}
      </div>
    </div>
  );
}
