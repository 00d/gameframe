'use client';
import React from 'react'
import className from 'classnames';

interface ButtonProps {
  children: React.ReactNode;
  primary?: boolean;
  secondary?: boolean;
  disabled?: boolean;
}

const Button = ({children, primary, secondary, disabled}: ButtonProps) => {
  const styling = className({
    'px-4 py-2 rounded': true,
    'bg-blue-500 text-white': primary,
    'bg-gray-500 text-white': secondary,
    'opacity-50 cursor-not-allowed': disabled,
  });

  return (
    <button className={styling} disabled={disabled}>
      {children}
    </button>
  );
}

export default Button;