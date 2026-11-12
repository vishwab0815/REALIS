import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 18, ...rest }: IconProps) {
  return {
    width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
    strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true, ...rest,
  };
}

export const IconUpload = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 16V4" /><path d="m6 10 6-6 6 6" /><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" /></svg>
);
export const IconImage = (p: IconProps) => (
  <svg {...base(p)}><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="m21 16-5-5-9 9" /></svg>
);
export const IconAudio = (p: IconProps) => (
  <svg {...base(p)}><path d="M4 10v4" /><path d="M8 7v10" /><path d="M12 4v16" /><path d="M16 8v8" /><path d="M20 11v2" /></svg>
);
export const IconVideo = (p: IconProps) => (
  <svg {...base(p)}><rect x="3" y="6" width="13" height="12" rx="2" /><path d="m16 10 5-3v10l-5-3" /></svg>
);
export const IconCheck = (p: IconProps) => <svg {...base(p)}><path d="m5 12 5 5 9-10" /></svg>;
export const IconAlert = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 3 2 20h20L12 3Z" /><path d="M12 10v4" /><path d="M12 17h.01" /></svg>
);
export const IconX = (p: IconProps) => <svg {...base(p)}><path d="M6 6l12 12M18 6 6 18" /></svg>;
export const IconChevron = (p: IconProps) => <svg {...base(p)}><path d="m9 6 6 6-6 6" /></svg>;
export const IconShield = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6l-8-3Z" /><path d="m9 12 2 2 4-4" /></svg>
);
export const IconSearch = (p: IconProps) => <svg {...base(p)}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>;
export const IconPlus = (p: IconProps) => <svg {...base(p)}><path d="M12 5v14M5 12h14" /></svg>;
export const IconFile = (p: IconProps) => (
  <svg {...base(p)}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5" /></svg>
);
export const IconExternal = (p: IconProps) => (
  <svg {...base(p)}><path d="M14 4h6v6" /><path d="M20 4 10 14" /><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>
);
export const IconPlay = (p: IconProps) => <svg {...base(p)}><path d="M7 5v14l11-7L7 5Z" fill="currentColor" stroke="none" /></svg>;
export const IconInfo = (p: IconProps) => (
  <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 8h.01" /></svg>
);
export const IconLayers = (p: IconProps) => (
  <svg {...base(p)}><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /></svg>
);
export const IconExpand = (p: IconProps) => (
  <svg {...base(p)}><path d="M15 3h6v6" /><path d="M9 21H3v-6" /><path d="m21 3-7 7" /><path d="m3 21 7-7" /></svg>
);

/** The REALIS mark: a lens with a check, "seeing what is real". */
export const LogoMark = ({ size = 26 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
    <defs>
      <linearGradient id="realis-g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#8ea2ff" />
        <stop offset="1" stopColor="#5ad1c6" />
      </linearGradient>
    </defs>
    <rect x="1" y="1" width="30" height="30" rx="9" fill="url(#realis-g)" />
    <circle cx="14.5" cy="14.5" r="7" fill="none" stroke="#0b0e14" strokeWidth="2.4" />
    <path d="m11.6 14.6 2.1 2.1 3.9-4" fill="none" stroke="#0b0e14" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    <path d="m19.6 19.6 4.4 4.4" stroke="#0b0e14" strokeWidth="2.6" strokeLinecap="round" />
  </svg>
);

export const MODALITY_ICON = { image: IconImage, audio: IconAudio, video: IconVideo } as const;
