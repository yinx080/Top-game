import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react'

import { sfx } from '../lib/sfx'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'primary' | 'danger' | 'ghost'
  size?: 'small' | 'normal' | 'big'
  block?: boolean
}

export function Button({
  variant = 'default',
  size = 'normal',
  block = false,
  className = '',
  onClick,
  ...rest
}: ButtonProps) {
  const classes = [
    'btn',
    variant !== 'default' && `btn--${variant}`,
    size !== 'normal' && `btn--${size}`,
    block && 'btn--block',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      type="button"
      className={classes}
      onClick={(event) => {
        sfx.play('click')
        onClick?.(event)
      }}
      {...rest}
    />
  )
}

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  hint?: string
  error?: string
}

export function Field({ label, hint, error, className = '', ...rest }: FieldProps) {
  const id = useId()
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <input id={id} className={`input ${className}`} {...rest} />
      {error ? (
        <span className="hint hint--error">{error}</span>
      ) : hint ? (
        <span className="hint">{hint}</span>
      ) : null}
    </div>
  )
}

export function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label className="toggle">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => {
          sfx.play('click')
          onChange(event.target.checked)
        }}
      />
      <span className="toggle__track" aria-hidden="true">
        <span className="toggle__knob" />
      </span>
      <span className="toggle__label">{label}</span>
    </label>
  )
}

export function Modal({
  open,
  title,
  onClose,
  children,
  width = 480,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  width?: number
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) onClose()
          }}
        >
          <motion.div
            className="panel overlay__panel"
            style={{ maxWidth: width }}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            initial={{ opacity: 0, y: 18, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.2, 1.1, 0.4, 1] }}
          >
            <div className="panel__head">
              <h2 className="panel__title">{title}</h2>
              <Button variant="ghost" size="small" onClick={onClose} aria-label="Cerrar">
                ✕
              </Button>
            </div>
            <div className="panel__body">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="spinner" role="status">
      <span className="spinner__dot" />
      <span className="spinner__dot" />
      <span className="spinner__dot" />
      {label && <span className="spinner__label">{label}</span>}
    </div>
  )
}

export function EmptyState({ icon, title, children }: { icon: string; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty__icon" aria-hidden="true">
        {icon}
      </span>
      <strong className="empty__title">{title}</strong>
      {children && <p className="hint">{children}</p>}
    </div>
  )
}
