import type {Account,Key,Resource,Row} from "./models";
export interface CabinetRepository {
  currentAdmin():Promise<Account>;
  login(data:Record<string,FormDataEntryValue>):Promise<Account>;
  logout():Promise<void>;
  keys():Promise<Key[]>;
  issueKey(data:{name:string;days:number}):Promise<{key:string}>;
  revokeKey(id:number):Promise<void>;
  list(resource:Resource):Promise<Row[]>;
  create(resource:Resource, data:unknown):Promise<{id:number}>;
}
