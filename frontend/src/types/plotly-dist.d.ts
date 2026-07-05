/**
 * plotly.js-dist-min ships no type declarations; map it onto the types of
 * the full plotly.js package (@types/plotly.js). The dist-min bundle is the
 * same API surface, prebuilt and minified.
 */
declare module 'plotly.js-dist-min' {
  import * as Plotly from 'plotly.js'
  export = Plotly
}
