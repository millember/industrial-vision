import React from "react";
import {createRoot} from "react-dom/client";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {App} from "./app/app";
import {RepositoryContext} from "./app/context";
import {cabinetRepository} from "./app/composition/repositories";
import "./style.css";
const client=new QueryClient({defaultOptions:{queries:{retry:false,refetchOnWindowFocus:false}}});
createRoot(document.getElementById("root")!).render(<React.StrictMode><RepositoryContext.Provider value={cabinetRepository}><QueryClientProvider client={client}><App/></QueryClientProvider></RepositoryContext.Provider></React.StrictMode>);
