import { createApp } from 'vue';
import router from './router';
import App from './App.vue';
import './styles/focus-page.css';

createApp(App).use(router).mount('#app');
