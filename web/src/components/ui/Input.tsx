import { cva, type VariantProps } from "class-variance-authority";
import React from "react";

const inputStyles = cva(
    [
        "w-full",
        "rounded-[var(--radius-sm)]",
        "bg-[var(--color-surface)]",
        "text-[var(--color-text)]",
        "px-3 py-2",
        "placeholder:text-[var(--color-muted)]",
        "border border-white/10",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]",
    ].join(" "),
    {
        variants: {
            size: { sm: "text-sm", md: "text-base" },
        },
        defaultVariants: { size: "md" },
    }
);

export type InputProps = React.InputHTMLAttributes<HTMLInputElement> &
    VariantProps<typeof inputStyles>;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
    ({ className, size, ...props }, ref) => {
        return <input ref={ref} className={inputStyles({ size, className })} {...props} />;
    }
);
Input.displayName = "Input";


