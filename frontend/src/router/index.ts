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
        { path: 'tools', name: 'tools', component: () => import('../views/Placeholder.vue'), props: { title: '软件工具' } },
        { path: 'actors', name: 'actors', component: () => import('../views/Placeholder.vue'), props: { title: '演员管理' } },
        { path: 'nfo', name: 'nfo', component: () => import('../views/Placeholder.vue'), props: { title: '信息管理' } },
        { path: 'settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
        { path: 'network', name: 'network', component: () => import('../views/NetworkView.vue') },
        { path: 'about', name: 'about', component: () => import('../views/AboutView.vue') },
      ],
    },
  ],
})

export default router
