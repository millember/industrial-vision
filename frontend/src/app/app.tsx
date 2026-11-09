import React,{useState} from "react";
import {useQuery,useQueryClient} from "@tanstack/react-query";
import type {Account,Resource,Row} from "../domain/models";
import {useRepository} from "./context";
type Field={name:string;label:string;type?:string;options?:{value:string;label:string}[];required?:boolean};
function DataForm({title,fields,onSave}:{title:string;fields:Field[];onSave:(data:Record<string,string>)=>Promise<void>}) {
 const [error,setError]=useState("");const [busy,setBusy]=useState(false);
 return <form onSubmit={async e=>{e.preventDefault();const form=e.currentTarget;setBusy(true);setError("");
  try{await onSave(Object.fromEntries(new FormData(form)) as Record<string,string>);form.reset();}
  catch(err){setError(err instanceof Error?err.message:"Ошибка запроса");}finally{setBusy(false);}}}>
  <h2>{title}</h2>{fields.map(f=><label key={f.name}>{f.label}{f.options?
   <select name={f.name} required={f.required!==false}>{f.options.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select>:
   <input name={f.name} type={f.type||"text"} required={f.required!==false} maxLength={f.type==="password"?256:4000}
    minLength={f.type==="password"?12:undefined} autoComplete={f.type==="password"?"new-password":"off"}/>}</label>)}
  {error&&<p role="alert" className="error">{error}</p>}<button disabled={busy}>{busy?"Сохраняем…":"Добавить"}</button>
 </form>;
}

function DataSection({path,title,fields,convert}:{path:Resource;title:string;fields:Field[];convert?:(d:Record<string,string>)=>unknown}) {
 const repo=useRepository();
 const q=useQuery({queryKey:[path],queryFn:()=>repo.list(path)});
 const qc=useQueryClient();
 return <div className="grid"><section className="panel"><h2>{title}</h2>{q.isPending?<p>Загрузка…</p>:q.isError?
  <p role="alert">Не удалось загрузить данные.</p>:q.data.length===0?<p>Записей пока нет.</p>:
  <div className="table-wrap"><table><thead><tr>{Object.keys(q.data[0]).map(k=><th key={k}>{k}</th>)}</tr></thead>
  <tbody>{q.data.map(row=><tr key={row.id as number}>{Object.values(row).map((v,i)=><td key={i}>{v===null?"—":String(v)}</td>)}</tr>)}</tbody></table></div>}</section>
  <section className="panel"><DataForm title={"Добавить: "+title.toLowerCase()} fields={fields} onSave={async d=>{await repo.create(path,convert?convert(d):d);await qc.invalidateQueries({queryKey:[path]});}}/></section></div>;
}

function Keys() {
 const repo=useRepository();
 const q=useQuery({queryKey:["keys"],queryFn:()=>repo.keys()});const qc=useQueryClient();
 const [secret,setSecret]=useState("");const [error,setError]=useState("");
 return <><div className="grid"><section className="panel"><h2>API-ключи администратора</h2><p>Ключ даёт доступ к API. Веб-кабинет и Swagger требуют входа администратора.</p>
 {q.isPending?<p>Загрузка…</p>:q.isError?<p role="alert">Не удалось загрузить ключи.</p>:q.data.map(k=><article className="key" key={k.id}><strong>{k.name}</strong><code>{k.prefix}…</code>
 <small>До {new Date(k.expires_at).toLocaleString("ru")}</small><span>{k.revoked?"Отозван":"Активен"}</span>
 {!k.revoked&&<button className="secondary" onClick={async()=>{try{await repo.revokeKey(k.id);setSecret("");await qc.invalidateQueries({queryKey:["keys"]});}catch(e){setError(String(e));}}}>Отозвать</button>}</article>)}
 {error&&<p role="alert" className="error">{error}</p>}</section>
 <section className="panel"><DataForm title="Создать API-ключ" fields={[{name:"name",label:"Название ключа"},{name:"days",label:"Срок действия, дней (1–365)",type:"number"}]}
 onSave={async d=>{setSecret("");const r=await repo.issueKey({name:d.name,days:Number(d.days)});setSecret(r.key);await qc.invalidateQueries({queryKey:["keys"]});}}/></section></div>
 {secret&&<section className="panel secret"><h2>Сохраните ключ сейчас</h2><p>Повторно получить полное значение нельзя. После закрытия или обновления страницы оно исчезнет.</p><code>{secret}</code><div className="actions">
 <button onClick={()=>void navigator.clipboard.writeText(secret)}>Копировать</button><button className="secondary" onClick={()=>setSecret("")}>Скрыть</button></div></section>}</>;
}

function Phone() {return <section className="panel"><h2>Подключение Android-приложения</h2><p>Телефону достаточно интернета. Tailscale и домашняя Wi-Fi-сеть не нужны.</p>
 <h3>Адрес сервера</h3><code>https://pet.oppennec.ru/industrial-vision/api/v1</code>
 <h3>Вход сотрудника</h3><p>Администратор создаёт пользователя и назначает цех. Приложение получает токен запросом:</p>
 <pre>{'POST /auth/token\nContent-Type: application/json\n\n{"login":"логин сотрудника","password":"его пароль"}'}</pre>
 <p>Из ответа взять access_token. Он действует 8 часов; после истечения нужно войти снова.</p>
 <h3>Авторизация запросов</h3><pre>{'GET /equipment\nAuthorization: Bearer <access_token>'}</pre>
 <p>Обычный пользователь получает данные своего цеха. Он не имеет доступа к веб-кабинету, ключам и Swagger. Для серверных интеграций администратор может использовать свой API-ключ в том же заголовке Bearer.</p>
 <h3>Пример Java</h3><pre>{'// Выполнять в фоновом потоке\nURL url = new URL(BASE_URL + "/equipment");\nHttpURLConnection c = (HttpURLConnection) url.openConnection();\nc.setConnectTimeout(10000);\nc.setReadTimeout(10000);\nc.setRequestProperty("Authorization", "Bearer " + token);\nint status = c.getResponseCode();\n// 401: войти повторно; 403: нет разрешения'}</pre>
 <p>В AndroidManifest.xml требуется разрешение android.permission.INTERNET. Проверку HTTPS-сертификата отключать не нужно. Пароли и токены не записывать в логи и исходники APK; токен хранить с защитой Android Keystore.</p>
 <p>На втором шаге доступны профиль и справочники. Приём фотографий и анализ ещё не реализованы.</p></section>;}

function Cabinet({user,onLogout}:{user:Account;onLogout:()=>Promise<void>}) {
 const repo=useRepository();
 const [tab,setTab]=useState("Ключи");const [error,setError]=useState("");
 const workshops=useQuery({queryKey:["workshops"],queryFn:()=>repo.list("workshops")});
 const types=useQuery({queryKey:["equipment-types"],queryFn:()=>repo.list("equipment-types")});
 const opts=(rows:Row[]|undefined)=>[{value:"",label:"Выберите…" },...(rows||[]).map(r=>({value:String(r.id),label:String(r.name)}))];
 const tabs=["Ключи","Пользователи","Цеха","Типы оборудования","Оборудование","Неисправности","Телефон"];
 return <><div className="heading"><div><span className="eyebrow">КАБИНЕТ АДМИНИСТРАТОРА</span><h1>Industrial Vision<span>.</span></h1><p>{user.full_name} · {user.login}</p></div><div className="actions">
 <a className="button secondary" href="/industrial-vision/docs">Swagger ↗</a><a className="button secondary" href="/industrial-vision/openapi.json">Схема API ↗</a>
 <button className="secondary" onClick={()=>void onLogout().catch(e=>setError(String(e)))}>Выйти</button></div></div>
 {error&&<p role="alert">{error}</p>}<nav aria-label="Разделы кабинета">{tabs.map(t=><button className={tab===t?"":"secondary"} key={t} onClick={()=>setTab(t)}>{t}</button>)}</nav>
 {tab==="Ключи"&&<Keys/>}
 {tab==="Пользователи"&&<DataSection path="users" title="Пользователи" fields={[{name:"login",label:"Логин"},{name:"full_name",label:"Имя"},{name:"password",label:"Пароль (от 12 символов)",type:"password"},{name:"role",label:"Роль",options:[{value:"WORKER",label:"Рабочий"},{value:"MASTER",label:"Мастер"},{value:"ENGINEER",label:"Инженер"},{value:"HEAD",label:"Начальник цеха"},{value:"ADMIN",label:"Администратор"}]},{name:"workshop_id",label:"Цех (обязателен сотруднику)",options:opts(workshops.data),required:false}]} convert={d=>({...d,workshop_id:d.workshop_id?Number(d.workshop_id):null})}/>}
 {tab==="Цеха"&&<DataSection path="workshops" title="Цеха" fields={[{name:"name",label:"Название цеха"}]}/>}
 {tab==="Типы оборудования"&&<DataSection path="equipment-types" title="Типы оборудования" fields={[{name:"name",label:"Название типа"}]}/>}
 {tab==="Оборудование"&&<DataSection path="equipment" title="Оборудование" fields={[{name:"name",label:"Название"},{name:"inventory_number",label:"Инвентарный номер"},{name:"workshop_id",label:"Цех",options:opts(workshops.data)},{name:"type_id",label:"Тип",options:opts(types.data)},{name:"passport",label:"Паспортные данные",required:false}]} convert={d=>({...d,workshop_id:Number(d.workshop_id),type_id:Number(d.type_id)})}/>}
 {tab==="Неисправности"&&<DataSection path="defect-types" title="Виды неисправностей" fields={[{name:"name",label:"Название"},{name:"status",label:"Предварительный статус",options:[{value:"WARNING",label:"Требует внимания"},{value:"CRITICAL",label:"Предварительно критический"}]},{name:"recommendation",label:"Рекомендация"}]}/>}
 {tab==="Телефон"&&<Phone/>}</>;
}

export function App() {
 const repo=useRepository();
 const me=useQuery({queryKey:["admin"],queryFn:()=>repo.currentAdmin()});
 const [error,setError]=useState("");const [busy,setBusy]=useState(false);const qc=useQueryClient();
 return <><header><a href="https://pet.oppennec.ru/">oppennec <small>LAB</small></a><a href="https://pet.oppennec.ru/">Все пет-проекты ↗</a></header><main>
 {me.isPending?<p role="status">Проверяем авторизацию…</p>:me.data?<Cabinet user={me.data} onLogout={async()=>{await repo.logout();qc.clear();window.location.reload();}}/>:
 <div className="login"><span className="eyebrow">INDUSTRIAL VISION / ШАГ 2</span><h1>Вход администратора<span>.</span></h1><p>Кабинет, API-ключи и схема сервера доступны только администратору. Аккаунты сотрудников предназначены для Android-приложения.</p>
 <form className="panel" onSubmit={async e=>{e.preventDefault();const form=e.currentTarget;const data=Object.fromEntries(new FormData(form));setBusy(true);setError("");try{const user=await repo.login(data);form.reset();qc.setQueryData(["admin"],user);}catch(err){setError(err instanceof Error?err.message:"Не удалось войти");}finally{setBusy(false);}}}>
 <label>Логин<input name="login" autoComplete="username" required maxLength={80}/></label><label>Пароль<input name="password" type="password" autoComplete="current-password" required maxLength={256}/></label>
 {error&&<p role="alert" className="error">{error}</p>}<button disabled={busy}>{busy?"Входим…":"Войти"}</button></form></div>}
 </main><footer>Industrial Vision · FastAPI / PostgreSQL / uv</footer></>;
}
