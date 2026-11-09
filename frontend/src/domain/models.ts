export type Account = {id:number;login:string;full_name:string;role:string;workshop_id:number|null};
export type Key = {id:number;name:string;prefix:string;created_at:string;expires_at:string;revoked:boolean};
export type Row=Record<string,string|number|boolean|null>;
export type Resource="users"|"workshops"|"equipment-types"|"equipment"|"defect-types";
