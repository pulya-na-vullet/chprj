import { createRoot } from "react-dom/client";
import "../styles/tokens.css";
import "./styles.css";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(<App />);
