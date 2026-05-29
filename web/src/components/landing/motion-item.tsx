"use client";

import { motion, type Variants } from "framer-motion";

/** Wrapper client per partecipare allo stagger di un StaggerGroup. */
export function MotionItem({
  children,
  variants,
  className,
}: {
  children: React.ReactNode;
  variants: Variants;
  className?: string;
}) {
  return (
    <motion.div variants={variants} className={className}>
      {children}
    </motion.div>
  );
}
