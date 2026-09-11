import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '../layouts/MainLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        { path: '', redirect: '/scrape' },
        { path: 'scrape', name: 'scrape', component: () => import('../views/ScrapeView.vue') },
        { path: 'log', name: 'log', component: () => import('../views/LogView.vue') },
        { path: 'tools', name: 'tools', component: () => import('../views/ToolsView.vue') },
        { path: 'actors', name: 'actors', component: () => import('../views/ActorManagerView.vue') },
        { path: 'nfo', name: 'nfo', component: () => import('../views/NfoLibraryView.vue') },
        { path: 'settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
        { path: 'network', name: 'network', component: () => import('../views/NetworkView.vue') },
        { path: 'about', name: 'about', component: () => import('../views/AboutView.vue') },
      ],
    },
  ],
})

export default router
