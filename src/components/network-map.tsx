'use client';
import {MapContainer,TileLayer,Marker,Popup,useMap} from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import {useEffect} from 'react';

type Point={id:string;name:string;lat:number;lng:number;kind:'listing'|'recipient'|'pickup'};
const icon=L.divIcon({className:'shareplate-map-pin',html:'<span></span>',iconSize:[18,18],iconAnchor:[9,9]});
function Fit({points}:{points:Point[]}){const map=useMap();useEffect(()=>{if(points.length)map.fitBounds(points.map(p=>[p.lat,p.lng] as [number,number]),{padding:[30,30]});},[map,points]);return null;}
export default function NetworkMap({points}:{points:Point[]}){return <div className="h-[420px] overflow-hidden rounded-2xl border border-[var(--line)]"><MapContainer center={[10.015,76.33]} zoom={12} scrollWheelZoom={false} className="h-full w-full"><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/><Fit points={points}/>{points.map(p=><Marker key={p.id} position={[p.lat,p.lng]} icon={icon}><Popup><strong>{p.name}</strong><br/><span className="text-xs">{p.kind}</span></Popup></Marker>)}</MapContainer></div>}
