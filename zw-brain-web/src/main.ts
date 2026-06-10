import { createApp } from 'vue';
import router from './router';
import App from './App.vue';
import { installGlobalErrorReporting } from './composables/useErrorReporting';
import './styles/focus-page.css';

const app = createApp(App).use(router);
installGlobalErrorReporting(app);
app.mount('#app');
