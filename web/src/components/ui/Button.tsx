import { cva, type VariantProps } from "class-variance-authority";
import React from "react";

const buttonStyles = cva(
    [
        "inline-flex items-center justify-center gap-2",
        "rounded-[var(--radius-sm)]",
        "px-3 py-2",
        "transition-colors duration-[var(--dur-base)] ease-[var(--ease-out)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]",
    ].join(" "),
    {
        variants: {
            variant: {
                primary: "bg-[var(--color-primary)] text-black hover:opacity-90",
                surface: "bg-[var(--color-surface)] text-[var(--color-text)] hover:opacity-95",
                ghost: "bg-transparent text-[var(--color-text)] hover:bg-white/5",
                danger: "bg-[var(--color-danger)] text-white hover:opacity-90",
            },
            size: {
                sm: "text-sm px-2 py-1",
                md: "text-sm px-3 py-2",
                lg: "text-base px-4 py-2.5",
            },
        },
        defaultVariants: {
            variant: "surface",
            size: "md",
        },
    }
);

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
    VariantProps<typeof buttonStyles> & {
        asChild?: boolean;
    };

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant, size, ...props }, ref) => {
        return (
            <button ref={ref} className={buttonStyles({ variant, size, className })} {...props} />
        );
    }
);
Button.displayName = "Button";


