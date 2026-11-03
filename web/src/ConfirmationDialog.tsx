import { useEffect, useId, useRef, useState } from "react";

export function ConfirmationDialog({
  title,
  description,
  label,
  destructive = false,
  disabled = false,
  onConfirm,
  onCancel,
}: {
  title: string;
  description: string;
  label: string;
  destructive?: boolean;
  disabled?: boolean;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}) {
  const id = useId(),
    dialog = useRef<HTMLDialogElement>(null),
    cancel = useRef<HTMLButtonElement>(null);
  const writing = useRef(false);
  const [pending, setPending] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    const element = dialog.current!;
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    element.showModal();
    cancel.current?.focus();
    return () => {
      element.close();
      if (previous?.isConnected && !previous.hasAttribute("disabled"))
        previous.focus({ preventScroll: true });
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="playlist-dialog confirm-dialog"
      role="alertdialog"
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-description`}
      onCancel={(event) => {
        event.preventDefault();
        if (!writing.current) onCancel();
      }}
      onClick={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        const outside =
          event.clientX < rect.left ||
          event.clientX > rect.right ||
          event.clientY < rect.top ||
          event.clientY > rect.bottom;
        if (event.target === event.currentTarget && outside && !writing.current)
          onCancel();
      }}
    >
      <h2 id={`${id}-title`}>{title}</h2>
      <p id={`${id}-description`}>{description}</p>
      <p className="confirm-error" role="alert">
        {error}
      </p>
      <div className="dialog-actions">
        <button
          ref={cancel}
          className="secondary"
          disabled={pending}
          onClick={onCancel}
        >
          キャンセル
        </button>
        <button
          className={`primary ${destructive ? "confirm-destructive" : ""}`}
          disabled={disabled || pending}
          onClick={async () => {
            if (writing.current) return;
            writing.current = true;
            setPending(true);
            setError("");
            try {
              await onConfirm();
            } catch (failure) {
              setError(
                failure instanceof Error
                  ? failure.message
                  : "操作を完了できませんでした。",
              );
            } finally {
              writing.current = false;
              setPending(false);
            }
          }}
        >
          {pending ? "処理中…" : label}
        </button>
      </div>
    </dialog>
  );
}
