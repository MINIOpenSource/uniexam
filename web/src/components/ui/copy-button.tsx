"use client";

import * as React from "react";
import { CheckIcon, CopyIcon } from "lucide-react";
import type { ButtonProps } from "@/components/ui/button";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { useTranslation } from "@/hooks/useTranslation";
import { cn } from "@/lib/utils";

interface CopyButtonProps extends Omit<ButtonProps, 'children'> {
  textToCopy: string | null | undefined;
  toastMessageKey?: string; // e.g., 'copyButton.toast.success.passcodeCopied'
  defaultToastMessageKey?: string; // e.g., 'copyButton.toast.success.description'
  className?: string;
  iconClassName?: string;
}

export function CopyButton({
  textToCopy,
  toastMessageKey,
  defaultToastMessageKey = 'copyButton.toast.success.description',
  className,
  iconClassName,
  variant = "ghost",
  size = "icon", // Default size for button component
  ...props
}: CopyButtonProps) {
  const { toast } = useToast();
  const { t } = useTranslation();
  const [hasCopied, setHasCopied] = React.useState(false);

  const onCopy = async () => {
    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setHasCopied(true);
      
      const valueForToast = textToCopy.length > 20 ? `${textToCopy.substring(0, 20)}...` : textToCopy;
      const description = toastMessageKey 
        ? t(toastMessageKey as any, { value: valueForToast }) 
        : t(defaultToastMessageKey as any, { value: valueForToast });

      toast({
        title: t('copyButton.toast.success.title'),
        description: description,
      });
      setTimeout(() => {
        setHasCopied(false);
      }, 2000); // Reset icon after 2 seconds
    } catch (error) {
      console.error("Failed to copy text: ", error);
      toast({
        title: t('copyButton.toast.error.title'),
        description: t('copyButton.toast.error.description'),
        variant: "destructive",
      });
    }
  };

  // Adjust icon size based on button size prop or a new prop if more granular control is needed.
  // For 'icon' size, lucide icons are typically h-4 w-4. For smaller buttons, we might want smaller icons.
  const finalIconClassName = cn(
    size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4", // Example: smaller icon for 'sm' button
    iconClassName
  );

  return (
    <Button
      variant={variant}
      size={size} // Use the Button's size prop
      className={cn(className)} // Allow overriding default padding/sizing via className if needed
      onClick={onCopy}
      disabled={!textToCopy || hasCopied}
      title={hasCopied ? t('copyButton.copied') : t('copyButton.copy')}
      {...props}
    >
      {hasCopied ? (
        <CheckIcon className={finalIconClassName} />
      ) : (
        <CopyIcon className={finalIconClassName} />
      )}
      <span className="sr-only">
        {hasCopied ? t('copyButton.copied') : t('copyButton.copy')}
      </span>
    </Button>
  );
}
