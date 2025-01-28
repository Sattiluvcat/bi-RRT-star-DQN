import numpy as np

from single_planning.Bi_RRT import check_collision, calc_p2l_xianduan_dis
from single_planning.VF_Bi_RRT_star import get_vector_field
from utils.node import Node


# 计算与障碍物的最近距离 --> checkCollision
def calc_obstacle_cost(trajectory, obstacles):
    # 根据config参数进行调整，当前取前方 0.5s 的轨迹进行判断
    print("trajectory:", trajectory)
    # 直接从轨迹数组计算，前三个点
    for i in range(2):
        start_pos = Node(trajectory[i, 0], trajectory[i, 1])
        end_pos = Node(trajectory[i + 1, 0], trajectory[i + 1, 1])
        print("start_pos:", start_pos, " end_pos:", end_pos)
        if check_collision(start_pos, end_pos, obstacles):
            return float("inf")
    return 0
    # if check_collision(start_pos, end_pos, obstacles):
    #     return float("inf")  # collision
    # return 0  # no collision


def calc_to_goal_cost(trajectory, goal):
    dx = goal[0] - trajectory[-1, 0]
    dy = goal[1] - trajectory[-1, 1]
    return np.hypot(dx, dy)


class DWA:
    def __init__(self, config, vector_field=None):
        self.config = config
        self.vector_field = vector_field

    def plan(self, x, goal, obstacles):
        # Dynamic Window [v_min, v_max, omega_min, omega_max]
        dw = self.calc_dynamic_window(x)
        u, trajectory = self.calc_control_and_trajectory(x, dw, goal, obstacles)
        return u, trajectory

    def calc_dynamic_window(self, x):
        # Dynamic window from robot specification
        Vs = [self.config['min_speed'], self.config['max_speed'],
              -self.config['max_yawrate'], self.config['max_yawrate']]

        # Dynamic window from motion model
        Vd = [x[3] - self.config['max_accel'] * self.config['dt'],
              x[3] + self.config['max_accel'] * self.config['dt'],
              x[4] - self.config['max_dyawrate'] * self.config['dt'],
              x[4] + self.config['max_dyawrate'] * self.config['dt']]

        # [v_min, v_max, omega_min, omega_max]
        dw = [max(Vs[0], Vd[0]), min(Vs[1], Vd[1]),
              max(Vs[2], Vd[2]), min(Vs[3], Vd[3])]

        return dw

    def calc_control_and_trajectory(self, x, dw, goal, obstacles):
        x_init = x[:]
        min_cost = float("inf")
        best_u = [0.0, 0.0]
        best_trajectory = np.array(x)

        # evaluate all trajectory with sampled input in dynamic window
        for v in np.arange(dw[0], dw[1], self.config['v_reso']):
            for y in np.arange(dw[2], dw[3], self.config['yawrate_reso']):
                trajectory = self.calc_trajectory(x_init, v, y)
                to_goal_cost = self.config['to_goal_cost_gain'] * calc_to_goal_cost(trajectory, goal)
                speed_cost = self.config['speed_cost_gain'] * (self.config['max_speed'] - trajectory[-1, 3])
                ob_cost = calc_obstacle_cost(trajectory, obstacles)
                # 向量场的cost——vf时设置
                field_cost = 0
                if self.vector_field is not None:
                    field_cost = self.config['field_gain'] * self.calc_vector_field_cost(trajectory)

                # cost最小的轨迹
                final_cost = to_goal_cost + speed_cost*15 + ob_cost + field_cost
                print("to_goal_cost:", to_goal_cost, " speed_cost:", speed_cost, " ob_cost:", ob_cost, " field_cost:",field_cost)
                if min_cost > final_cost != float('inf'):
                    min_cost = final_cost
                    best_u = [v, y]
                    best_trajectory = trajectory
        print("找到了一条好路")
        return best_u, best_trajectory

    # 检查方法是否能评价向量场内轨迹
    def calc_vector_field_cost(self, trajectory):
        total_cost = 0
        for point in trajectory:
            x, y = point[0], point[1]
            u, v = get_vector_field(x,y,self.vector_field)
            if np.isnan(u) or np.isnan(v):
                continue
            direction_vector_field = np.arctan2(v, u)
            direction_trajectory = np.arctan2(point[1] - trajectory[0][1], point[0] - trajectory[0][0])
            total_cost += abs(direction_trajectory - direction_vector_field)
        return total_cost

    def calc_trajectory(self, x_init, v, y):
        trajectory = np.array(x_init)
        x = np.array(x_init)
        time = 0
        while time <= self.config['predict_time']:
            x = self.motion(x, [v, y])
            trajectory = np.vstack((trajectory, x))
            time += self.config['dt']
        return trajectory

    def motion(self, x, u):
        x[2] += u[1] * self.config['dt']
        x[0] += u[0] * np.cos(x[2]) * self.config['dt']
        x[1] += u[0] * np.sin(x[2]) * self.config['dt']
        x[3] = u[0]
        x[4] = u[1]
        return x
