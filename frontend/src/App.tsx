import { ArrowRight, LayoutDashboard, Ticket } from 'lucide-react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import Logo from './Logo'
import OperatorLogin from './operator/Login'
import OperatorShell from './operator/Shell'
import Allocation from './operator/pages/Allocation'
import Audit from './operator/pages/Audit'
import Carpool from './operator/pages/Carpool'
import DisruptionMap from './operator/pages/DisruptionMap'
import Explanations from './operator/pages/Explanations'
import Groups from './operator/pages/Groups'
import HeatMap from './operator/pages/HeatMap'
import Overview from './operator/pages/Overview'
import Passengers from './operator/pages/Passengers'
import Preferences from './operator/pages/Preferences'
import Simulation from './operator/pages/Simulation'
import Unresolved from './operator/pages/Unresolved'
import Vehicles from './operator/pages/Vehicles'
import PassengerLogin from './passenger/Login'
import PassengerShell from './passenger/Shell'
import CarpoolPage from './passenger/pages/Carpool'
import Home from './passenger/pages/Home'
import NewJourney from './passenger/pages/NewJourney'
import Notifications from './passenger/pages/Notifications'
import Options from './passenger/pages/Options'

function Landing() {
  return (
    <div className="px-root flex min-h-full flex-col">
      <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col justify-center gap-10 px-4 py-10 md:px-8">
        <div>
          <p className="flex items-center gap-2.5 font-display text-[17px] font-semibold"><Logo /> The Stranded Network</p>
          <h1 className="mt-8 max-w-2xl text-[30px] font-bold leading-[38px] tracking-tight md:text-[40px] md:leading-[48px]">
            Your service was cancelled. Let's get you there.
          </h1>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Link to="/app" className="group flex flex-col gap-3 rounded-2xl bg-px-high p-6 hover:bg-px-highest">
            <span className="flex size-10 items-center justify-center rounded-xl bg-px-accent text-white"><Ticket size={20} /></span>
            <h2 className="text-[22px] font-semibold leading-7 tracking-tight">Passenger app</h2>
            <p className="flex-1 text-px-muted">
              Compare your options, rank what suits you, and follow your journey. Or offer a spare seat if you're
              already heading that way.
            </p>
            <span className="inline-flex items-center gap-2 font-semibold text-px-accent">
              Open the app <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
            </span>
          </Link>
          <Link to="/operator" className="group flex flex-col gap-3 rounded-2xl bg-px-card p-6 shadow-card hover:bg-px-low">
            <span className="flex size-10 items-center justify-center rounded-xl bg-px-mid text-px-accent"><LayoutDashboard size={20} /></span>
            <h2 className="text-[22px] font-semibold leading-7 tracking-tight">Operator console</h2>
            <p className="flex-1 text-px-muted">
              One disruption. Limited seats. Every decision explained. Group passengers, allocate replacement capacity
              without overbooking, and route unmet demand to community carpools.
            </p>
            <span className="inline-flex items-center gap-2 font-semibold text-px-accent">
              Open the console <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
            </span>
          </Link>
        </div>
        <p className="text-xs font-semibold uppercase tracking-wider text-px-muted">Simulated network · Demo data</p>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />

      <Route path="/login" element={<PassengerLogin />} />
      <Route path="/app" element={<PassengerShell />}>
        <Route index element={<Home />} />
        <Route path="journey/new" element={<NewJourney />} />
        <Route path="journey/:id/options" element={<Options />} />
        <Route path="carpool" element={<CarpoolPage />} />
        <Route path="notifications" element={<Notifications />} />
      </Route>

      <Route path="/operator/login" element={<OperatorLogin />} />
      <Route path="/operator" element={<OperatorShell />}>
        <Route index element={<Overview />} />
        <Route path="map" element={<DisruptionMap />} />
        <Route path="heatmap" element={<HeatMap />} />
        <Route path="passengers" element={<Passengers />} />
        <Route path="groups" element={<Groups />} />
        <Route path="vehicles" element={<Vehicles />} />
        <Route path="allocation" element={<Allocation />} />
        <Route path="preferences" element={<Preferences />} />
        <Route path="simulation" element={<Simulation />} />
        <Route path="unresolved" element={<Unresolved />} />
        <Route path="carpool" element={<Carpool />} />
        <Route path="explanations" element={<Explanations />} />
        <Route path="audit" element={<Audit />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
