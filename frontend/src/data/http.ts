export async function api<T>(path:string, method="GET", body?:unknown):Promise<T> {
  const response=await fetch("/industrial-vision/api/v1/"+path,{
    method,credentials:"same-origin",cache:"no-store",
    headers:{"Content-Type":"application/json","X-IV-Client":"browser"},
    body:body===undefined?undefined:JSON.stringify(body),
    signal:AbortSignal.timeout(15000),
  });
  if(!response.ok){
    const data:unknown=await response.json().catch(()=>null);
    const message=typeof data==="object"&&data!==null&&"detail" in data&&typeof data.detail==="string"?data.detail:
      response.status===401?"Войдите как администратор":"Не удалось выполнить запрос";
    throw new Error(message);
  }
  return response.status===204?undefined as T:response.json() as Promise<T>;
}
