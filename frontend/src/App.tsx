import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { SelectionProvider } from './state/SelectionContext'
import Layout from './components/Layout'
import NuclideChart from './components/NuclideChart/NuclideChart'
import XSViewer from './components/XSViewer/XSViewer'
import ComparisonPanel from './components/ComparisonPanel/ComparisonPanel'
import DecayChainGraph from './components/DecayChainGraph/DecayChainGraph'
import FissionYieldsView from './components/FissionYieldsView/FissionYieldsView'

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <NuclideChart /> },
      { path: '/xs', element: <XSViewer /> },
      { path: '/compare', element: <ComparisonPanel /> },
      { path: '/decay', element: <DecayChainGraph /> },
      { path: '/yields', element: <FissionYieldsView /> },
    ],
  },
])

export default function App() {
  return (
    <SelectionProvider>
      <RouterProvider router={router} />
    </SelectionProvider>
  )
}
