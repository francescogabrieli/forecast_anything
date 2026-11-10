import { renderToStaticMarkup } from 'react-dom/server';
import { App } from './App';

export const render = () => renderToStaticMarkup(<App />);
