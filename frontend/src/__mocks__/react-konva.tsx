// Mock for react-konva to allow Jest tests to run without a canvas environment.
import React from "react";

const noop = () => null;

export const Stage: React.FC<{ children?: React.ReactNode; [key: string]: unknown }> = ({ children }) => (
  <div data-testid="konva-stage">{children}</div>
);
export const Layer: React.FC<{ children?: React.ReactNode }> = ({ children }) => (
  <div>{children}</div>
);
export const Rect = noop;
export const Circle = noop;
export const Text = noop;
export const Line = noop;
export const Group: React.FC<{ children?: React.ReactNode; [key: string]: unknown }> = ({ children }) => (
  <div>{children}</div>
);
