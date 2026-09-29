import React from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider, Show } from "@clerk/react";
import App, { Welcome } from "./App";
import "./styles.css";

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {publishableKey ? (
      <ClerkProvider publishableKey={publishableKey}>
        <Show when="signed-out">
          <Welcome />
        </Show>
        <Show when="signed-in">
          <App />
        </Show>
      </ClerkProvider>
    ) : (
      <main className="config-error">
        <h1>Setup required</h1>
        <p>Add a Clerk publishable key to start the app.</p>
      </main>
    )}
  </React.StrictMode>,
);
