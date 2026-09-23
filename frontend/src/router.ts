import { createRouter, createWebHistory } from 'vue-router'
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./features/workbench/WorkbenchView.vue') },
    { path: '/projects', component: () => import('./features/projects/ProjectsView.vue') },
    { path: '/data', component: () => import('./features/data/DataView.vue') },
    { path: '/runs', component: () => import('./features/runs/RunsView.vue') },
    { path: '/runs/:id', component: () => import('./features/runs/RunDetailView.vue') },
  ],
})
