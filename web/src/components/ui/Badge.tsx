import { cva, type VariantProps } from "class-variance-authority";
import React from "react";

const badgeStyles = cva(
    [
        "inline-flex items-center gap-1",
        "rounded-[var(--radius-sm)]",
        "px-2 py-0.5 text-xs",
        "border border-white/10",
    ].join(" "),
    {
        variants: {
            variant: {
                neutral: "bg-surface text-muted",
                info: "bg-surface text-primary",
                danger: "bg-surface text-[var(--color-danger)]",
            },
            tone: {
                solid: "",
                subtle: "opacity-80",
            },
        },
        defaultVariants: { variant: "neutral", tone: "solid" },
    }
);

export type BadgeProps = React.HTMLAttributes<HTMLSpanElement> &
    VariantProps<typeof badgeStyles>;

export const Badge = ({ className, variant, tone, ...props }: BadgeProps) => (
    <span role="status" aria-live="polite" className={badgeStyles({ variant, tone, className })} {...props} />
);


