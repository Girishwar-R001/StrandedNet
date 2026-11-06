import { ArrowRight } from 'lucide-react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
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
    <div className="grid min-h-full md:grid-cols-2">
      <Link to="/app" className="px-root group flex flex-col justify-between gap-16 p-8 md:p-12">
        <p className="font-semibold">The Stranded Network</p>
        <div>
          <h1 className="max-w-md text-4xl font-semibold leading-tight tracking-tight md:text-5xl">
            Your service was cancelled. Let's get you there.
          </h1>
          <p className="mt-4 max-w-sm text-px-muted">
            Compare your options, rank what suits you, and follow your journey. Or offer a spare seat if you're
            already heading that way.
          </p>
          <span className="mt-8 inline-flex items-center gap-2 font-medium text-px-accent">
            Passenger app <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
          </span>
        </div>
      </Link>
      <Link to="/operator" className="op-root group flex flex-col justify-between gap-16 p-8 md:p-12">
        <p className="num text-xs text-op-muted">SIMULATED NETWORK · DEMO DATA</p>
        <div>
          <h2 className="max-w-md text-3xl font-medium leading-tight tracking-tight md:text-4xl">
            One disruption. Limited seats. Every decision explained.
          </h2>
          <p className="mt-4 max-w-sm text-sm text-op-muted">
            Group passengers, allocate replacement capacity without overbooking, and route unmet demand to community
            carpools.
          </p>
          <span className="mt-8 inline-flex items-center gap-2 text-sm font-medium text-op-signal">
            Operator console <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
          </span>
        </div>
      </Link>
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
