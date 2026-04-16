import React from "react";
import { render, screen } from "@testing-library/react";
import App from "./App";

test("renders ProcViz upload panel", () => {
  render(<App />);
  expect(screen.getByText(/ProcViz/i)).toBeInTheDocument();
});

test("renders domain selector buttons", () => {
  render(<App />);
  expect(screen.getByText(/Mining/i)).toBeInTheDocument();
  expect(screen.getByText(/Healthcare/i)).toBeInTheDocument();
  expect(screen.getByText(/Defence/i)).toBeInTheDocument();
});
