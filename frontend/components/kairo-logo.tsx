interface Props {
  size?: number;
}

export default function KairoLogo({ size = 64 }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 80 80"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="kairo"
      role="img"
    >
      {/* Hexagon frame */}
      <polygon
        points="40,4 72,22 72,58 40,76 8,58 8,22"
        stroke="#8B5CF6"
        strokeWidth="1.5"
        fill="rgba(139,92,246,0.08)"
      />
      {/* Dashed inner ring */}
      <circle
        cx="40"
        cy="40"
        r="24"
        stroke="#06B6D4"
        strokeWidth="0.75"
        strokeDasharray="3 4"
      />
      {/* Katakana カ */}
      <text
        x="40"
        y="52"
        textAnchor="middle"
        fontFamily="serif"
        fontSize="30"
        fontWeight="700"
        fill="#EDE9FE"
      >
        カ
      </text>
      {/* Circuit accent lines */}
      <line x1="40" y1="76" x2="40" y2="68" stroke="#06B6D4" strokeWidth="1" />
      <line x1="8"  y1="22" x2="16" y2="27" stroke="#06B6D4" strokeWidth="1" />
      <line x1="72" y1="22" x2="64" y2="27" stroke="#06B6D4" strokeWidth="1" />
    </svg>
  );
}
