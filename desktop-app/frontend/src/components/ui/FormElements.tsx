import { type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes, type ReactNode } from 'react';

interface FormGroupProps {
  label?: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}

export function FormGroup({ label, hint, children, className = '' }: FormGroupProps) {
  return (
    <div className={`mb-6 ${className}`}>
      {label && (
        <label className="block font-medium mb-2.5 text-text">{label}</label>
      )}
      {children}
      {hint && (
        <span className="block text-xs text-text-secondary mt-2">{hint}</span>
      )}
    </div>
  );
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

export function Input({ className = '', ...props }: InputProps) {
  return (
    <input
      className={`w-full px-3 py-2.5 bg-bg-input border border-border rounded-md text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-border-focus ${className}`}
      {...props}
    />
  );
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  children: ReactNode;
}

export function Select({ className = '', children, ...props }: SelectProps) {
  return (
    <select
      className={`w-full px-3 py-2.5 bg-bg-input border border-border rounded-md text-sm text-text focus:outline-none focus:border-border-focus ${className}`}
      {...props}
    >
      {children}
    </select>
  );
}

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {}

export function Textarea({ className = '', ...props }: TextareaProps) {
  return (
    <textarea
      className={`w-full px-3 py-2.5 bg-bg-input border border-border rounded-md text-sm text-text placeholder:text-text-muted focus:outline-none focus:border-border-focus resize-y ${className}`}
      {...props}
    />
  );
}

interface CheckboxProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export function Checkbox({ label, className = '', ...props }: CheckboxProps) {
  return (
    <label className={`flex items-center gap-2 cursor-pointer ${className}`}>
      <input
        type="checkbox"
        className="w-4 h-4 accent-accent-blue"
        {...props}
      />
      <span className="text-sm text-text">{label}</span>
    </label>
  );
}

interface FormSectionProps {
  title: string;
  hint?: string;
  children: ReactNode;
}

export function FormSection({ title, hint, children }: FormSectionProps) {
  return (
    <div className="bg-bg-secondary rounded-lg p-5 mb-6">
      <h4 className="text-sm font-semibold text-text mb-2">{title}</h4>
      {hint && (
        <p className="text-xs text-text-secondary mb-5">{hint}</p>
      )}
      {children}
    </div>
  );
}

interface FormRowProps {
  children: ReactNode;
}

export function FormRow({ children }: FormRowProps) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {children}
    </div>
  );
}

interface DayCheckboxesProps {
  name: string;
  selectedDays: number[];
  onChange: (days: number[]) => void;
}

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function DayCheckboxes({ name, selectedDays, onChange }: DayCheckboxesProps) {
  const handleChange = (day: number, checked: boolean) => {
    if (checked) {
      onChange([...selectedDays, day].sort());
    } else {
      onChange(selectedDays.filter((d) => d !== day));
    }
  };

  return (
    <div className="flex flex-wrap gap-3">
      {DAY_NAMES.map((dayName, index) => (
        <label key={index} className="flex items-center gap-1 cursor-pointer text-sm">
          <input
            type="checkbox"
            name={name}
            value={index}
            checked={selectedDays.includes(index)}
            onChange={(e) => handleChange(index, e.target.checked)}
            className="w-4 h-4 accent-accent-blue"
          />
          <span className="text-text">{dayName}</span>
        </label>
      ))}
    </div>
  );
}
