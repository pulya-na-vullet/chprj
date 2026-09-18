type Props = {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
  disabled?: boolean;
};

export function Switch({ checked, onChange, label, disabled }: Props) {
  return (
    <label className={`switch${disabled ? " switch-disabled" : ""}`}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        aria-label={label}
      />
      <span className="switch-track" />
      <span className="switch-thumb" />
    </label>
  );
}
