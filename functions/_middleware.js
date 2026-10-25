import {websiteGate} from "../shared/site-gate.js";
export async function onRequest(context){const paused=await websiteGate(context.request,"baseball");return paused||context.next();}
