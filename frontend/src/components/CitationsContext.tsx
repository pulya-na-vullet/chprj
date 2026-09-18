import { createContext, useContext } from "react";
import type { Citation } from "../api/types";

const CitationsContext = createContext<Citation[]>([]);

export const CitationsProvider = CitationsContext.Provider;
export const useCitations = () => useContext(CitationsContext);
