import { useEffect,useMemo,useState } from "react";
import { Outlet,createRootRoute,createRoute,createRouter } from "@tanstack/react-router";
import { useQuery,useQueryClient } from "@tanstack/react-query";
import { AppContextProvider } from "./app-context";
import { TokenGate } from "./components/auth/token-gate";
import { AppShell } from "./components/layout/app-shell";
import { ApiError,apiFetch } from "./lib/api";
import { clearAccessToken,clearCachedBootstrap,readAccessToken,readCachedBootstrap,saveAccessToken,saveCachedBootstrap } from "./lib/session";
import { purgeTeacherOfflinePartition } from "./lib/teacher-offline-store";
import { teacherOfflinePartitionKey } from "./teacher-offline-core";
import { ContextPage } from "./pages/context-page";
import { HomePage } from "./pages/home-page";
import { InterventionWorkspacePage } from "./pages/intervention-workspace-page";
import { Student360Page } from "./pages/student-360-page";
import { SuggestionInboxPage } from "./pages/suggestion-inbox-page";
import { WorkspacePage } from "./pages/workspace-page";
import { CopilotWorkspacePage } from "./pages/copilot-workspace-page";
import { IntegrationWorkspacePage } from "./pages/integration-workspace-page";
import type { UiBootstrap } from "./types/bootstrap";

function RootLayout(){const queryClient=useQueryClient();const[authRevision,setAuthRevision]=useState(0);const token=readAccessToken();const q=useQuery({queryKey:["ui-bootstrap",token,authRevision],queryFn:()=>apiFetch<UiBootstrap>("/api/v1/ui/bootstrap"),enabled:Boolean(token),retry:false});useEffect(()=>{if(q.data)saveCachedBootstrap(q.data);},[q.data]);const cached=readCachedBootstrap();const authFailure=q.error instanceof ApiError&&(q.error.status===401||q.error.status===403);const bootstrap=q.data??(q.isError&&!authFailure?cached:null);function submitToken(next:string){clearCachedBootstrap();saveAccessToken(next);queryClient.clear();setAuthRevision(v=>v+1);}async function signOut(){if(bootstrap)await purgeTeacherOfflinePartition(teacherOfflinePartitionKey(bootstrap));clearAccessToken();queryClient.clear();setAuthRevision(v=>v+1);}const errorMessage=useMemo(()=>{if(!q.error)return undefined;if(q.error instanceof ApiError){if(q.error.status===401||q.error.status===403)return"El token no tiene un contexto válido para Education OS.";return`No fue posible iniciar la sesión: ${q.error.message}`;}return"No fue posible iniciar la sesión.";},[q.error]);if(!token)return<TokenGate initialToken="" errorMessage={undefined} onSubmit={submitToken}/>;if(q.isError&&!bootstrap)return<TokenGate initialToken={token} errorMessage={errorMessage} onSubmit={submitToken}/>;if(!bootstrap)return<main className="flex min-h-screen items-center justify-center"><div className="rounded-2xl border border-slate-200 bg-white px-6 py-5 text-sm font-semibold text-slate-600 shadow-sm">Cargando contexto institucional…</div></main>;return<AppContextProvider value={{bootstrap,signOut}}><AppShell><Outlet/></AppShell></AppContextProvider>}
const rootRoute=createRootRoute({component:RootLayout});
const indexRoute=createRoute({getParentRoute:()=>rootRoute,path:"/",component:HomePage});
const contextRoute=createRoute({getParentRoute:()=>rootRoute,path:"/context",component:ContextPage});
const workspaceRoute=createRoute({getParentRoute:()=>rootRoute,path:"/workspace/$moduleId",component:WorkspaceRouteComponent});
const suggestionInboxRoute=createRoute({getParentRoute:()=>rootRoute,path:"/m21/suggestions",component:SuggestionInboxPage});
const student360Route=createRoute({getParentRoute:()=>rootRoute,path:"/m21/students/$studentProfileId",component:Student360RouteComponent});
const interventionWorkspaceRoute=createRoute({getParentRoute:()=>rootRoute,path:"/m21/interventions/$interventionId",component:InterventionWorkspaceRouteComponent});
const copilotRoute=createRoute({getParentRoute:()=>rootRoute,path:"/copilot",component:CopilotWorkspacePage});
function WorkspaceRouteComponent(){const{moduleId}=workspaceRoute.useParams();return moduleId==="copilot"?<CopilotWorkspacePage/>:moduleId==="integrations"?<IntegrationWorkspacePage/>:<WorkspacePage moduleId={moduleId}/>;}
function Student360RouteComponent(){const{studentProfileId}=student360Route.useParams();return<Student360Page studentProfileId={studentProfileId}/>;}
function InterventionWorkspaceRouteComponent(){const{interventionId}=interventionWorkspaceRoute.useParams();return<InterventionWorkspacePage interventionId={interventionId}/>;}
const routeTree=rootRoute.addChildren([indexRoute,contextRoute,workspaceRoute,suggestionInboxRoute,student360Route,interventionWorkspaceRoute,copilotRoute]);
export const router=createRouter({routeTree,basepath:"/app",defaultPreload:"intent",defaultPreloadStaleTime:0});
declare module "@tanstack/react-router"{interface Register{router:typeof router}}
