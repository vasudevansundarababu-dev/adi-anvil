import { useEffect, useId, useRef, useState } from 'react';
import type { FormHTMLAttributes } from 'react';

type Control = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;

export default function Form({
  children,
  onSubmit,
  ...props
}: FormHTMLAttributes<HTMLFormElement>) {
  const formId = useId();
  const ref = useRef<HTMLFormElement>(null),
    summary = useRef<HTMLDivElement>(null);
  const [errors, setErrors] = useState<{ id: string; label: string; message: string }[]>([]);
  useEffect(() => {
    ref.current?.querySelectorAll<Control>('input,textarea,select').forEach((control) => {
      control.setAttribute('aria-required', String(control.required));
      const label = control.labels?.[0];
      if (!label) return;
      let marker = label.querySelector('[data-required-indicator]');
      if (control.required && !marker) {
        marker = document.createElement('span');
        marker.setAttribute('data-required-indicator', '');
        marker.textContent = ' * Required';
        label.append(marker);
      } else if (!control.required) marker?.remove();
    });
  });
  function validate(only?: Control) {
    const controls = Array.from(
      ref.current?.querySelectorAll<Control>('input,textarea,select') || [],
    );
    const next = only ? errors.filter((e) => e.id !== only.id) : [];
    for (const control of only ? [only] : controls) {
      if (!control.id) control.id = formId + '-field-' + controls.indexOf(control);
      const valid = control.disabled || control.validity.valid;
      control.setAttribute('aria-invalid', String(!valid));
      if (!valid) {
        const label =
          control.labels?.[0]?.textContent?.replace(' * Required', '') || control.name || 'Field';
        control.setAttribute('aria-describedby', control.id + '-error');
        next.push({
          id: control.id,
          label,
          message: control.validationMessage || 'Check this value.',
        });
      } else if (control.getAttribute('aria-describedby') === control.id + '-error')
        control.removeAttribute('aria-describedby');
    }
    setErrors(next);
    return next.length === 0;
  }
  return (
    <form
      {...props}
      ref={ref}
      noValidate
      onInput={(e) => {
        props.onInput?.(e);
        const control = e.target;
        if (
          (control instanceof HTMLInputElement ||
            control instanceof HTMLTextAreaElement ||
            control instanceof HTMLSelectElement) &&
          control.getAttribute('aria-invalid') === 'true'
        )
          validate(control);
      }}
      onBlur={(e) => {
        if (
          e.target instanceof HTMLInputElement ||
          e.target instanceof HTMLTextAreaElement ||
          e.target instanceof HTMLSelectElement
        )
          validate(e.target);
      }}
      onSubmit={(e) => {
        if (!validate()) {
          e.preventDefault();
          requestAnimationFrame(() => summary.current?.focus());
          return;
        }
        onSubmit?.(e);
      }}
    >
      <p className="muted">* indicates a required field</p>
      {!!errors.length && (
        <div ref={summary} tabIndex={-1} role="alert" className="banner error">
          <strong>Correct these fields:</strong>
          <ul>
            {errors.map((error) => (
              <li key={error.id} id={error.id + '-error'}>
                <a
                  href={'#' + error.id}
                  onClick={(e) => {
                    e.preventDefault();
                    document.getElementById(error.id)?.focus();
                  }}
                >
                  {error.label}: {error.message}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      {children}
    </form>
  );
}
