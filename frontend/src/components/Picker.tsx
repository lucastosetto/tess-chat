import { Fragment, useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "../icons";

type Option = { value: string; label: string; group?: string };

type Props = {
  label: string;
  options: Option[];
  value: string;
  fallback?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
};

export function Picker({
  label,
  options,
  value,
  fallback,
  disabled,
  onChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const current = value || fallback || "";
  const shown = fallback ? options.filter((o) => o.value) : options;
  const selected = options.find((o) => o.value === current);

  useEffect(() => {
    if (!open) return;
    (
      menu.current?.querySelector<HTMLButtonElement>(
        '[aria-selected="true"]',
      ) ?? menu.current?.querySelector("button")
    )?.focus();
    const close = (event: MouseEvent) => {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const pick = (next: string) => {
    setOpen(false);
    onChange(next === fallback ? "" : next);
  };

  return (
    <span className="pk-wrap" ref={wrap}>
      <button
        type="button"
        className="chip pk"
        data-tip={label}
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen(!open)}
      >
        <span>{selected?.label ?? ""}</span>
        <ChevronDown />
      </button>
      {open && (
        <div
          className="menu pk-menu"
          role="listbox"
          aria-label={label}
          ref={menu}
          onKeyDown={(e) => {
            const items = [...(menu.current?.querySelectorAll("button") ?? [])];
            const i = items.indexOf(
              document.activeElement as HTMLButtonElement,
            );
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              items[
                (i + (e.key === "ArrowDown" ? 1 : -1) + items.length) %
                  items.length
              ]?.focus();
            }
            if (e.key === "Escape") {
              e.preventDefault();
              setOpen(false);
            }
          }}
        >
          {shown.map((o, i) => (
            <Fragment key={o.value}>
              {o.group && o.group !== shown[i - 1]?.group && (
                <div className="who">{o.group}</div>
              )}
              <button
                type="button"
                role="option"
                aria-selected={o.value === current}
                onClick={() => pick(o.value)}
              >
                {o.label}
                {o.value === current && (
                  <span className="check">
                    <Check />
                  </span>
                )}
              </button>
            </Fragment>
          ))}
        </div>
      )}
    </span>
  );
}
