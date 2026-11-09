import {createContext,useContext} from "react";
import type {CabinetRepository} from "../domain/repository";
export const RepositoryContext=createContext<CabinetRepository|null>(null);
export function useRepository(){const repo=useContext(RepositoryContext);if(!repo)throw new Error("Repository provider missing");return repo;}
